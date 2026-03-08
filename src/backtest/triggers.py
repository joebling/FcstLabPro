"""Trigger strategies."""

from __future__ import annotations

import numpy as np


class TriggerStrategy:
    """触发策略基类."""
    
    def should_monitor(self, idx, prob):
        """是否开始监控."""
        raise NotImplementedError
    
    def should_enter(self, idx, close_prices, monitor_start_idx):
        """是否入场."""
        raise NotImplementedError
    
    def monitor_expired(self, idx, monitor_start_idx):
        """监控是否过期."""
        raise NotImplementedError


class BaselineTrigger(TriggerStrategy):
    """Baseline 策略：预测>0.5 就入场."""
    
    def __init__(self, prob_threshold=0.5):
        self.prob_threshold = prob_threshold
    
    def should_monitor(self, idx, prob):
        return prob > self.prob_threshold
    
    def should_enter(self, idx, close_prices, monitor_start_idx):
        return True
    
    def monitor_expired(self, idx, monitor_start_idx):
        return False


class TriggerA(TriggerStrategy):
    """触发方案 A：等待 dip ≥ threshold 再入场."""
    
    def __init__(self, prob_threshold=0.7, dip_threshold=0.04, monitor_days=10):
        self.prob_threshold = prob_threshold
        self.dip_threshold = dip_threshold
        self.monitor_days = monitor_days
    
    def should_monitor(self, idx, prob):
        return prob > self.prob_threshold
    
    def should_enter(self, idx, close_prices, monitor_start_idx):
        if idx < monitor_start_idx + 1:
            return False
        
        prices_since_monitor = close_prices[monitor_start_idx:idx+1]
        peak = np.max(prices_since_monitor)
        current = prices_since_monitor[-1]
        drawdown = (peak - current) / peak
        
        return drawdown >= self.dip_threshold
    
    def monitor_expired(self, idx, monitor_start_idx):
        return idx - monitor_start_idx >= self.monitor_days
