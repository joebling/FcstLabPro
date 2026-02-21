"""Metrics calculation."""

import numpy as np


def calculate_metrics(returns, cumulative):
    """
    计算回测指标.
    
    Parameters
    ----------
    returns : np.ndarray
        日收益率数组
    cumulative : np.ndarray
        累积收益率数组
        
    Returns
    -------
    dict
        指标字典
    """
    if len(returns) == 0 or np.std(returns) == 0:
        return {
            'sharpe': 0.0,
            'total_return': 0.0,
            'max_dd': 0.0,
            'win_rate': 0.0,
            'annual_return': 0.0,
            'annual_vol': 0.0
        }
    
    total_return = cumulative[-1] - 1
    sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)
    
    peak = np.maximum.accumulate(cumulative)
    drawdown = (peak - cumulative) / peak
    max_dd = np.max(drawdown)
    
    win_rate = np.mean(returns > 0) if len(returns) > 0 else 0.0
    annual_return = (cumulative[-1]) ** (252 / len(returns)) - 1 if len(returns) > 0 else 0.0
    annual_vol = np.std(returns) * np.sqrt(252)
    
    return {
        'sharpe': sharpe,
        'total_return': total_return,
        'max_dd': max_dd,
        'win_rate': win_rate,
        'annual_return': annual_return,
        'annual_vol': annual_vol
    }
