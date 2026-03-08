"""Backtest engine."""

from __future__ import annotations

import numpy as np
import pandas as pd


class BacktestEngine:
    """回测引擎."""
    
    def __init__(self, close_prices, prob_scores):
        """
        初始化回测引擎.
        
        Parameters
        ----------
        close_prices : np.ndarray
            收盘价数组
        prob_scores : np.ndarray
            预测概率数组
        """
        self.close_prices = np.array(close_prices)
        self.prob_scores = np.array(prob_scores)
        self.n = len(close_prices)
        
    def run(self, trigger_strategy, exit_strategy, initial_position=0, position_sizer=None):
        """
        运行回测.
        
        Parameters
        ----------
        trigger_strategy : TriggerStrategy
            触发策略
        exit_strategy : ExitStrategy
            退出策略
        initial_position : float, optional
            初始仓位, by default 0
        position_sizer : callable, optional
            仓位计算函数, by default None
            
        Returns
        -------
        dict
            回测结果
        """
        positions = np.zeros(self.n)
        entry_prices = np.full(self.n, np.nan)
        exit_prices = np.full(self.n, np.nan)
        entry_indices = []
        exit_indices = []
        
        current_position = initial_position
        entry_price = np.nan
        entry_idx = -1
        monitor_active = False
        monitor_start_idx = -1
        
        for i in range(self.n):
            positions[i] = current_position
            
            if current_position == 0:
                if trigger_strategy.should_monitor(i, self.prob_scores[i]):
                    if not monitor_active:
                        monitor_active = True
                        monitor_start_idx = i
                
                if monitor_active:
                    if trigger_strategy.should_enter(i, self.close_prices, monitor_start_idx):
                        if position_sizer is not None:
                            size = position_sizer(self.prob_scores[i])
                        else:
                            size = 1.0
                        current_position = size
                        entry_price = self.close_prices[i]
                        entry_idx = i
                        entry_prices[i] = entry_price
                        entry_indices.append(i)
                        exit_strategy.on_enter(i, entry_price)
                        monitor_active = False
                    elif trigger_strategy.monitor_expired(i, monitor_start_idx):
                        monitor_active = False
            
            else:
                exit_signal = exit_strategy.should_exit(i, self.close_prices[i])
                if exit_signal:
                    current_position = 0
                    exit_prices[i] = self.close_prices[i]
                    exit_indices.append(i)
                    exit_strategy.on_exit(i)
        
        returns = []
        for i in range(self.n - 1):
            ret = (self.close_prices[i+1] - self.close_prices[i]) / self.close_prices[i]
            returns.append(positions[i] * ret)
        
        returns = np.array(returns)
        
        if len(returns) == 0:
            return {
                'positions': positions,
                'returns': returns,
                'cumulative': np.array([1.0]),
                'entry_indices': entry_indices,
                'exit_indices': exit_indices,
                'entry_prices': entry_prices,
                'exit_prices': exit_prices
            }
        
        cumulative = (1 + returns).cumprod()
        
        return {
            'positions': positions,
            'returns': returns,
            'cumulative': cumulative,
            'entry_indices': entry_indices,
            'exit_indices': exit_indices,
            'entry_prices': entry_prices,
            'exit_prices': exit_prices
        }
