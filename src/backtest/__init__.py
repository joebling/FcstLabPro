"""Backtest module."""

from __future__ import annotations
from .engine import BacktestEngine
from .triggers import TriggerStrategy, BaselineTrigger, TriggerA
from .exits import ExitStrategy, BaselineExit, TP_SL_Exit, FixedHoldExit
from .metrics import calculate_metrics

__all__ = [
    'BacktestEngine',
    'TriggerStrategy',
    'BaselineTrigger',
    'TriggerA',
    'ExitStrategy',
    'BaselineExit',
    'TP_SL_Exit',
    'FixedHoldExit',
    'calculate_metrics'
]
