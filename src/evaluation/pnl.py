"""PnL 回测指标计算模块."""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class PnLMetrics:
    """PnL 指标集合."""
    total_return: float
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    num_trades: int
    num_wins: int
    num_losses: int


def calculate_pnl_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    returns: Optional[np.ndarray] = None,
    prices: Optional[pd.Series] = None,
    position_size: float = 1.0,
    transaction_cost: float = 0.001,
    risk_free_rate: float = 0.0,
    periods_per_year: float = 52.0,
) -> PnLMetrics:
    """计算 PnL 指标.

    Parameters
    ----------
    y_true : np.ndarray
        真实标签 (0/1)
    y_pred : np.ndarray
        预测标签 (0/1)
    returns : np.ndarray, optional
        资产收益率序列。如果不提供，需要提供 prices。
    prices : pd.Series, optional
        价格序列。如果不提供，需要提供 returns。
    position_size : float
        仓位大小 (0-1)
    transaction_cost : float
        交易成本比例
    risk_free_rate : float
        无风险利率 (年化)
    periods_per_year : float
        每年交易周期数

    Returns
    -------
    PnLMetrics
        PnL 指标
    """
    # 计算收益率序列
    if returns is None:
        if prices is None:
            raise ValueError("需要提供 returns 或 prices")
        returns = prices.pct_change().values

    # 过滤有效数据
    valid_mask = ~(np.isnan(y_true) | np.isnan(y_pred) | np.isnan(returns))
    y_true = y_true[valid_mask]
    y_pred = y_pred[valid_mask]
    returns = returns[valid_mask]

    if len(returns) == 0:
        logger.warning("没有有效数据计算 PnL")
        return PnLMetrics(
            total_return=0, cagr=0, sharpe=0, sortino=0,
            max_drawdown=0, calmar=0, win_rate=0, profit_factor=0,
            avg_win=0, avg_loss=0, num_trades=0, num_wins=0, num_losses=0,
        )

    # 计算策略收益
    # y_pred=1 表示做多, y_pred=0 表示空仓/做空
    # 这里简化: 1=买入信号, 0=不持仓
    position = y_pred * position_size

    # 策略收益 = 持仓 * 资产收益 - 交易成本
    trade_signal = np.diff(np.concatenate([[0], position]))
    costs = np.abs(trade_signal) * transaction_cost
    strategy_returns = position[:-1] * returns[1:] - costs[1:]

    # 累计收益
    cumulative = np.cumprod(1 + strategy_returns)
    total_return = cumulative[-1] - 1 if len(cumulative) > 0 else 0

    # 年化收益率 (CAGR)
    n_periods = len(strategy_returns)
    years = n_periods / periods_per_year
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

    # 夏普比率
    excess_returns = strategy_returns - risk_free_rate / periods_per_year
    std_returns = np.std(excess_returns)
    sharpe = np.mean(excess_returns) / std_returns * np.sqrt(periods_per_year) if std_returns > 0 else 0

    # 索提诺比率 (只考虑下行波动)
    negative_returns = excess_returns[excess_returns < 0]
    downside_std = np.std(negative_returns) if len(negative_returns) > 0 else 0
    sortino = np.mean(excess_returns) / downside_std * np.sqrt(periods_per_year) if downside_std > 0 else 0

    # 最大回撤
    peak = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - peak) / peak
    max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0

    # Calmar 比率
    calmar = cagr / abs(max_drawdown) if max_drawdown != 0 else 0

    # 交易统计
    trade_returns = strategy_returns[strategy_returns != 0]
    wins = trade_returns[trade_returns > 0]
    losses = trade_returns[trade_returns < 0]

    num_trades = len(trade_returns)
    num_wins = len(wins)
    num_losses = len(losses)
    win_rate = num_wins / num_trades if num_trades > 0 else 0

    # 盈亏比
    avg_win = np.mean(wins) if len(wins) > 0 else 0
    avg_loss = np.mean(losses) if len(losses) > 0 else 0
    profit_factor = abs(np.sum(wins) / np.sum(losses)) if np.sum(losses) != 0 else 0

    metrics = PnLMetrics(
        total_return=total_return,
        cagr=cagr,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_drawdown,
        calmar=calmar,
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_win=avg_win,
        avg_loss=avg_loss,
        num_trades=num_trades,
        num_wins=num_wins,
        num_losses=num_losses,
    )

    logger.info(f"PnL 指标: Return={total_return:.2%}, Sharpe={sharpe:.2f}, "
                f"MaxDD={max_drawdown:.2%}, WinRate={win_rate:.2%}")

    return metrics


def add_pnl_to_evaluation(
    bt_result,
    prices: Optional[pd.Series] = None,
    returns: Optional[np.ndarray] = None,
):
    """为回测结果添加 PnL 指标.

    Parameters
    ----------
    bt_result : BacktestResult
        回测结果
    prices : pd.Series, optional
        价格序列
    returns : np.ndarray, optional
        收益率序列

    Returns
    -------
    dict
        PnL 指标字典
    """
    if bt_result.all_y_true is None or bt_result.all_y_pred is None:
        return {}

    pnl = calculate_pnl_metrics(
        y_true=bt_result.all_y_true,
        y_pred=bt_result.all_y_pred,
        returns=returns,
        prices=prices,
    )

    return {
        "pnl_total_return": pnl.total_return,
        "pnl_cagr": pnl.cagr,
        "pnl_sharpe": pnl.sharpe,
        "pnl_sortino": pnl.sortino,
        "pnl_max_drawdown": pnl.max_drawdown,
        "pnl_calmar": pnl.calmar,
        "pnl_win_rate": pnl.win_rate,
        "pnl_profit_factor": pnl.profit_factor,
        "pnl_num_trades": pnl.num_trades,
    }
