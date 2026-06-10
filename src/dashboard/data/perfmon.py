"""实盘业绩监控数据层 — 专业 live monitoring (区别于研究态 IC 验证).

设计原则 (量化监控, 非 alpha 验证):
  1. 净值曲线 + 回撤 = 业绩 ground truth (比点估计胜率信息量大得多)
  2. 样本量 gating: n<MIN_SAMPLE 时统计量仅供监控, 不可当 alpha 判据
  3. Live vs Backtest 对照 = 核心衰减警报 (实盘 vs 回测预期)
  4. 退出方式拆解 = 哪种退出在创造价值

数据源:
  - 实盘: ${FCST_DATA_DIR}/state/{model}_state.json 的 history[] (真实成交)
  - 回测基准: models/production/{model}/pnl_metrics.json
绝不把实盘数字回流调参 (守机构手册 §2.2 OOS 锁定)。
"""
from __future__ import annotations

import json

from src.dashboard.config import PROJECT_ROOT
from src.dashboard.data import ledger

# 统计量达到机构可信度的最小成交笔数 (低于此仅供监控, 不下结论)
MIN_SAMPLE = 20


def _equity_and_drawdown(trades: list[dict]) -> dict:
    """从真实成交 pnl 序列算净值曲线 + 回撤序列.

    净值: equity_0=1.0, equity_i = equity_{i-1} * (1+pnl_i) (按 exit_date 升序)。
    回撤: dd_i = equity_i / running_max - 1。
    """
    rows = sorted(
        [t for t in trades if t.get("exit_date") and t.get("pnl") is not None],
        key=lambda t: t["exit_date"],
    )
    dates, equity, dd = [], [], []
    eq, peak = 1.0, 1.0
    for t in rows:
        eq *= (1.0 + float(t["pnl"]))
        peak = max(peak, eq)
        dates.append(t["exit_date"])
        equity.append(round(eq, 4))
        dd.append(round(eq / peak - 1.0, 4))
    max_dd = min(dd) if dd else 0.0
    return {
        "dates": dates,
        "equity": equity,
        "drawdown": dd,
        "total_return": round(eq - 1.0, 4),
        "max_drawdown": round(max_dd, 4),
    }


def backtest_baseline(model_name: str, variant: str | None = None) -> dict:
    """读回测基准 (pnl_metrics.json), 按 variant 选合适的策略口径.

    conservative → 优先含 'regime' 的口径; 否则取 '无开关' 纯模型基准。
    """
    p = PROJECT_ROOT / "models" / "production" / model_name / "pnl_metrics.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    if not data:
        return {}

    key = None
    is_cons = (variant or "").lower().startswith("conserv")
    if is_cons:
        key = next((k for k in data if "regime" in k), None)
    if key is None:
        key = next((k for k in data if "无开关" in k), None) or next(iter(data))
    b = data.get(key, {})
    return {
        "label": key,
        "win_rate": b.get("win_rate"),
        "avg_trade_return": b.get("avg_trade_return"),
        "max_drawdown": b.get("max_drawdown"),
        "sharpe": b.get("sharpe"),
        "exposure": b.get("exposure"),
        "num_trades": b.get("num_trades"),
    }


def build(model_name: str, variant: str | None = None) -> dict:
    """组装实盘监控视图."""
    state = ledger.load_state(model_name)
    trades = state.get("history", [])
    n = len(trades)
    curve = _equity_and_drawdown(trades)

    wins = sum(1 for t in trades if (t.get("pnl") or 0) > 0)
    pnls = [float(t["pnl"]) for t in trades if t.get("pnl") is not None]
    avg_pnl = sum(pnls) / len(pnls) if pnls else 0.0
    win_rate = wins / n if n else 0.0

    # 退出方式拆解 (复用 ledger 的口径)
    exit_stats = ledger.trade_history(model_name).get("exit_stats", {})

    # 弱耦合研究视图: LightGBM 真实成交按开仓日 RR regime 切片。
    regime_slices = ledger.trade_history_by_cycle_regime(model_name)
    regime_slice_n = sum(r.get("count", 0) for r in regime_slices)
    regime_slice_sample_ok = regime_slice_n >= MIN_SAMPLE
    regime_slice_low_n = any(0 < r.get("count", 0) < 5 for r in regime_slices)

    bt = backtest_baseline(model_name, variant)

    # Live vs Backtest 对照 (n 足够才有意义)
    cmp_rows = []
    if bt:
        def _row(name, live, base, fmt, higher_better=True):
            delta = None
            if live is not None and base is not None:
                delta = live - base
            return {"name": name, "live": live, "base": base,
                    "delta": delta, "fmt": fmt, "higher_better": higher_better}
        cmp_rows = [
            _row("胜率", win_rate, bt.get("win_rate"), "pct"),
            _row("均盈/笔", avg_pnl, bt.get("avg_trade_return"), "pct2"),
            _row("最大回撤", curve["max_drawdown"], bt.get("max_drawdown"), "pct", higher_better=True),
        ]

    return {
        "has_state": bool(state),
        "n_trades": n,
        "sample_ok": n >= MIN_SAMPLE,
        "min_sample": MIN_SAMPLE,
        "win_rate": win_rate,
        "avg_pnl": avg_pnl,
        "total_return": curve["total_return"],
        "max_drawdown": curve["max_drawdown"],
        "curve": curve,
        "exit_stats": exit_stats,
        "regime_slices": regime_slices,
        "regime_slice_n": regime_slice_n,
        "regime_slice_sample_ok": regime_slice_sample_ok,
        "regime_slice_low_n": regime_slice_low_n,
        "backtest": bt,
        "cmp_rows": cmp_rows,
        "in_position": state.get("in_position", False),
    }
