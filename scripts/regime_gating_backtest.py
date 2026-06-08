#!/usr/bin/env python3
"""Phase 3a (Case A) Regime Gating 回测.

对比: E20c 裸跑 vs E20c + MVRV-Z regime gating.
核心问题: regime gating 能否改善回撤 (MaxDD) 而不劣化 Sharpe?

方法:
  1. 复用 E20c config 跑 walk-forward, 记录每个 OOS 样本的 **日期**.
  2. 用 MVRV-Z regime (顶部区减仓) 给每日仓位乘 regime 系数.
  3. 对比裸策略 vs gating 策略的 Sharpe / MaxDD / Calmar.

防未来函数: regime 用滚动分位 + shift(1) (见 src/strategy/onchain_regime.py).

验证门槛 (phase3 §5): MaxDD 改善 ≥ 10% 且 Sharpe 不劣化.

用法:
    .venv/bin/python scripts/regime_gating_backtest.py \\
        --config models/production/e20c-conservative-prune/config.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logging import setup_logging  # noqa: E402
from src.data.loader import load_csv  # noqa: E402
from src.data.splitter import walk_forward_split  # noqa: E402
from src.features.builder import build_features, get_feature_columns  # noqa: E402
from src.labels.registry import get_label_strategy  # noqa: E402
import src.labels.directional_filtered  # noqa: E402,F401  (注册 label)
from src.models.registry import create_model  # noqa: E402
from src.strategy.onchain_regime import (  # noqa: E402
    classify_regime,
    regime_position_multiplier,
)
import yaml  # noqa: E402


def _pnl_stats(strategy_returns: np.ndarray, periods_per_year: float = 252.0) -> dict:
    """从日度策略收益算 Sharpe / MaxDD / Calmar / CAGR."""
    r = strategy_returns[~np.isnan(strategy_returns)]
    if len(r) == 0:
        return dict(sharpe=0, max_dd=0, calmar=0, cagr=0, total=0)
    cum = np.cumprod(1 + r)
    total = cum[-1] - 1
    years = len(r) / periods_per_year
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 else 0
    std = np.std(r)
    sharpe = np.mean(r) / std * np.sqrt(periods_per_year) if std > 0 else 0
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    max_dd = dd.min()
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0
    return dict(sharpe=sharpe, max_dd=max_dd, calmar=calmar, cagr=cagr, total=total)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, help="E20c config 路径")
    ap.add_argument("--mvrv", default="data/external/onchain/mvrv_zscore_data.csv")
    ap.add_argument("--top-mult", type=float, default=0.3, help="顶部区仓位乘子")
    ap.add_argument("--cost", type=float, default=0.001, help="单边交易成本")
    args = ap.parse_args()

    setup_logging()
    cfg = yaml.safe_load(open(args.config))

    # ---- 1. 数据 + 特征 + 标签 (复刻 runner 数据链) ----
    data_cfg = cfg["data"]
    df = load_csv(
        data_cfg["path"],
        start=data_cfg.get("start"),
        end=data_cfg.get("end"),
        expected_sha256=data_cfg.get("expected_sha256"),
        strict_sha=True,
    )
    feat_cfg = cfg["features"]
    df = build_features(
        df,
        feature_sets=feat_cfg["sets"],
        drop_na_method=feat_cfg.get("drop_na_method", "ffill_then_drop"),
        drop_features=feat_cfg.get("drop_features"),
    )
    label_cfg = cfg["label"]
    import inspect
    label_func = get_label_strategy(label_cfg["strategy"])
    _accepted = set(inspect.signature(label_func).parameters.keys()) - {"df"}
    _kwargs = {k: v for k, v in label_cfg.items() if k != "strategy" and k in _accepted}
    labels = label_func(df, **_kwargs)
    df["label"] = labels
    df = df.dropna(subset=["label"])
    df["label"] = df["label"].astype(int)

    feature_cols = get_feature_columns(df)
    X = df[feature_cols].values
    y = df["label"].values.astype(int)
    dates = df.index
    close = df["close"]

    # ---- 2. Walk-Forward, 记录每个 OOS 样本的日期 ----
    eval_cfg = cfg["evaluation"]
    model_cfg = cfg["model"]
    seed = cfg.get("seed", 42)
    np.random.seed(seed)

    folds = walk_forward_split(
        len(X),
        init_train=eval_cfg.get("init_train", 800),
        oos_window=eval_cfg.get("oos_window", 63),
        step=eval_cfg.get("step", 21),
    )
    purge = eval_cfg.get("purge_gap", 0)

    oos_idx: list[int] = []
    oos_pred: list[int] = []
    for f in folds:
        tr_end = f.train_end - purge
        Xtr, ytr = X[: tr_end], y[: tr_end]
        Xte = X[f.test_start : f.test_end]
        m = create_model(model_cfg["type"], model_cfg.get("params", {}))
        m.fit(Xtr, ytr)
        pred = m.predict(Xte)
        oos_idx.extend(range(f.test_start, f.test_end))
        oos_pred.extend(np.asarray(pred).astype(int).tolist())

    oos = pd.DataFrame({"pred": oos_pred}, index=dates[oos_idx])
    # 去重 (相邻 fold 的 oos 可能重叠, 保留最后)
    oos = oos[~oos.index.duplicated(keep="last")].sort_index()

    # ---- 3. 对齐 MVRV-Z regime ----
    mvrv = pd.read_csv(args.mvrv, parse_dates=["date"]).set_index("date")["value"]
    regime = classify_regime(mvrv, min_periods=365, hysteresis=0.05, shift=True)
    regime = regime.reindex(oos.index, method="ffill")
    mult = regime_position_multiplier(regime, top_mult=args.top_mult).fillna(1.0)

    # ---- 4. 日度收益 + 成本 ----
    ret = close.reindex(oos.index).pct_change().shift(-1)  # 次日收益 (t 持仓吃 t→t+1)
    pos_raw = oos["pred"].astype(float)
    pos_gated = pos_raw * mult.values

    def _strat_ret(pos: pd.Series) -> np.ndarray:
        trade = pos.diff().abs().fillna(pos.abs())
        costs = trade * args.cost
        return (pos * ret - costs).values

    r_raw = _strat_ret(pos_raw)
    r_gated = _strat_ret(pos_gated)

    s_raw = _pnl_stats(r_raw)
    s_gated = _pnl_stats(r_gated)

    # ---- 5. 报告 ----
    print("\n" + "=" * 64)
    print("  Phase 3a Regime Gating 回测: E20c 裸跑 vs +MVRV-Z gating")
    print("=" * 64)
    print(f"  OOS 样本: {len(oos)} 天 ({oos.index[0].date()} ~ {oos.index[-1].date()})")
    print(f"  顶部区减仓至: {args.top_mult:.0%} | 成本: {args.cost:.1%}/边")
    rc = regime.reindex(oos.index, method="ffill").value_counts(normalize=True)
    print(f"  OOS regime 占比: {rc.round(3).to_dict()}")
    print("-" * 64)
    print(f"  {'指标':<14}{'裸跑':>14}{'+gating':>14}{'变化':>16}")
    print("-" * 64)

    def _row(name, a, b, pct=True, higher_better=True):
        if pct:
            chg = f"{(b - a) * 100:+.1f}pp"
            print(f"  {name:<14}{a:>13.2%}{b:>14.2%}{chg:>16}")
        else:
            chg = f"{(b - a):+.3f}"
            print(f"  {name:<14}{a:>13.2f}{b:>14.2f}{chg:>16}")

    _row("Sharpe", s_raw["sharpe"], s_gated["sharpe"], pct=False)
    _row("MaxDD", s_raw["max_dd"], s_gated["max_dd"])
    _row("Calmar", s_raw["calmar"], s_gated["calmar"], pct=False)
    _row("CAGR", s_raw["cagr"], s_gated["cagr"])
    _row("TotalRet", s_raw["total"], s_gated["total"])
    print("-" * 64)

    # ---- 6. 门槛判定 ----
    dd_improve = (abs(s_raw["max_dd"]) - abs(s_gated["max_dd"])) / abs(s_raw["max_dd"]) if s_raw["max_dd"] else 0
    sharpe_ok = s_gated["sharpe"] >= s_raw["sharpe"] - 1e-9
    print(f"  MaxDD 改善: {dd_improve:+.1%} (门槛 ≥ +10%)")
    print(f"  Sharpe 不劣化: {'✅' if sharpe_ok else '❌'} "
          f"({s_gated['sharpe']:.2f} vs {s_raw['sharpe']:.2f})")
    verdict = "✅ 通过 (gating 有效)" if (dd_improve >= 0.10 and sharpe_ok) else "❌ 未达门槛"
    print(f"  判定: {verdict}")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()
