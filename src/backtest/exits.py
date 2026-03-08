"""Exit strategies."""

from __future__ import annotations

import numpy as np


class ExitStrategy:
    """退出策略基类."""
    
    def on_enter(self, idx, entry_price):
        """入场时调用."""
        raise NotImplementedError
    
    def should_exit(self, idx, current_price):
        """是否退出."""
        raise NotImplementedError
    
    def on_exit(self, idx):
        """退出时调用."""
        raise NotImplementedError


class BaselineExit(ExitStrategy):
    """Baseline 策略：一直持有到下一个预测."""
    
    def __init__(self):
        pass
    
    def on_enter(self, idx, entry_price):
        pass
    
    def should_exit(self, idx, current_price):
        return False
    
    def on_exit(self, idx):
        pass


class TP_SL_Exit(ExitStrategy):
    """止盈止损 + 时间止损."""
    
    def __init__(self, tp=0.06, sl=0.05, time_stop=14):
        self.tp = tp
        self.sl = sl
        self.time_stop = time_stop
        self.entry_price = None
        self.entry_idx = None
    
    def on_enter(self, idx, entry_price):
        self.entry_price = entry_price
        self.entry_idx = idx
    
    def should_exit(self, idx, current_price):
        if self.entry_price is None:
            return False
        
        ret = (current_price - self.entry_price) / self.entry_price
        
        if ret >= self.tp:
            return True
        
        if ret <= -self.sl:
            return True
        
        if idx - self.entry_idx >= self.time_stop:
            return True
        
        return False
    
    def on_exit(self, idx):
        self.entry_price = None
        self.entry_idx = None


class FixedHoldExit(ExitStrategy):
    """固定持仓期."""
    
    def __init__(self, hold_days=14):
        self.hold_days = hold_days
        self.entry_idx = None
    
    def on_enter(self, idx, entry_price):
        self.entry_idx = idx
    
    def should_exit(self, idx, current_price):
        if self.entry_idx is None:
            return False
        return idx - self.entry_idx >= self.hold_days
    
    def on_exit(self, idx):
        self.entry_idx = None
