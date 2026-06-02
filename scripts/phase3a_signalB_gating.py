#!/usr/bin/env python3
"""Phase 3a: 信号B (MVRV-Z 动量转负) 软减仓叠加 E20c — 含 2021 顶 OOS.

关键: init_train 调小 (默认 250), 让 OOS 覆盖 2021-11 双顶 + 2025 顶,
才能真正检验 "确认顶减仓" 的价值 (原 init_train=800 的 OOS 无顶, 见 §3.1 CONCLUSION).

软减仓: 信号B触发后 hold_days 天内, 仓位 × cut_mult (默认 0.3).
对比: 裸 E20c vs +信号B减仓 的 Sharpe / MaxDD / Calmar.

防未来函数: MVRV-Z shift(1); 信号触发当日收盘后才知, 次日起减仓.

用法:
    .venv/bin/python scripts/phase3a_signalB_gating.py
"""
from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logging import setup_logging  # noqa: E402
from src.data.loader import load_csv  # noqa: E402
from src.data.splitter import walk_forward_split  # noqa: E402
from src.features.builder import build_features, get_feature_columns  # noqa: E402
from src.labels.registry import get_label_strategy  # noqa: E402
import src.labels.directional_filtered  # noqa: E402,F401
from src.models.registry import create_model  # noqa: E402


def _stats(r: np.ndarray, ppy: float = 252.0) -> dict:
    r = r[~np.isnan(r)]
    if len(r) == 0:
        return dict(sharpe=0, max_dd=0, calmar=0, cagr=0, total=0)
    cum = np.cumprod(1 + r)
    total = cum[-1] - 1
    yrs = len(r) / ppy
    cagr = (1 + total) ** (1 / yrs) - 1 if yrs > 0 else 0
    sh = np.mean(r) / np.std(r) * np.sqrt(ppy) if np.std(r) > 0 else 0
    dd = ((cum - np.maximum.accumulate(cum)) / np.maximum.accumulate(cum)).min()
    calmar = cagr / abs(dd) if dd != 0 else 0
    return dict(sharpe=sh, max_dd=dd, calmar=calmar, cagr=cagr, total=total)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="models/production/e20c-conservative-prune/config.yaml")
    ap.add_argument("--init-train", type=int, default=250, help="调小以含2021顶")
    ap.add_argument("--hold-days", type=int, default=63, help="信号后减仓持续天数")
    ap.add_argument("--cut-mult", type=float, default=0.3, help="减仓乘子")
    ap.add_argument("--cost", type=float, default=0.001)
    args = ap.parse_args()

    setup_logging()
    cfg = yaml.safe_load(open(args.config))
    dc = cfg["data"]
    df = load_csv(dc["path"], start=dc.get("start"), end=dc.get("end"),
                  expected_sha256=dc.get("expected_sha256"), strict_sha=True)
    fc = cfg["features"]
    df = build_features(df, feature_sets=fc["sets"],
                        drop_na_method=fc.get("drop_na_method", "ffill_then_drop"),
                        drop_features=fc.get("drop_features"))
    lc = cfg["label"]
    lf = get_label_strategy(lc["strategy"])
    acc = set(inspect.signature(lf).parameters) - {"df"}
    df["label"] = lf(df, **{k: v for k, v in lc.items() if k != "strategy" and k in acc})
    df = df.dropna(subset=["label"])
    df["label"] = df["label"].astype(int)

    cols = get_feature_columns(df)
    X, y, dates, close = df[cols].values, df["label"].values.astype(int), df.index, df["close"]

    ec, mc = cfg["evaluation"], cfg["model"]
    np.random.seed(cfg.get("seed", 42))
    folds = walk_forward_split(len(X), args.init_train,
                               ec.get("oos_window", 63), ec.get("step", 21))
    purge = ec.get("purge_gap", 0)
    oi, op = [], []
    for f in folds:
        m = create_model(mc["type"], mc.get("params", {}))
        m.fit(X[: f.train_end - purge], y[: f.train_end - purge])
        op.extend(np.asarray(m.predict(X[f.test_start:f.test_end])).astype(int))
        oi.extend(range(f.test_start, f.test_end))
    oos = pd.DataFrame({"pred": op}, index=dates[oi])
    oos = oos[~oos.index.duplicated(keep="last")].sort_index()

    # 信号B: MVRV-Z 90日动量转负 (shift1防未来), 触发后 hold_days 减仓
    mvrv = pd.read_csv("data/external/onchain/mvrv_zscore_data.csv",
                       parse_dates=["date"]).set_index("date")["value"]
    m1 = mvrv.shift(1)
    mom90 = m1 - m1.rolling(90).mean()
    sigB = ((mom90 < -0.2) & (mom90.shift(10) > 0)).reindex(oos.index, method="ffill").fillna(False)

    # 构造减仓乘子: 信号触发当日及之后 hold_days 天 = cut_mult
    mult = pd.Series(1.0, index=oos.index)
    trig_idx = np.where(sigB.values)[0]
    for ti in trig_idx:
        mult.iloc[ti: ti + args.hold_days] = args.cut_mult

    ret = close.reindex(oos.index).pct_change().shift(-1)
    pos_raw = oos["pred"].astype(float)
    pos_gated = pos_raw * mult.values

    def _r(pos):
        tr = pos.diff().abs().fillna(pos.abs())
        return (pos * ret - tr * args.cost).values

    s_raw = _stats(_r(pos_raw))
    s_gat = _stats(_r(pos_gated))

    n_cut_days = int((mult < 1.0).sum())
    print("\n" + "=" * 64)
    print("  Phase 3a: 信号B 软减仓叠加 E20c (含 2021 顶 OOS)")
    print("=" * 64)
    print(f"  init_train={args.init_train} | OOS: {oos.index[0].date()}~{oos.index[-1].date()} ({len(oos)}天)")
    print(f"  信号B触发: {len(trig_idx)}次 | 减仓天数: {n_cut_days} | 减仓至{args.cut_mult:.0%}, 持续{args.hold_days}天")
    print("-" * 64)
    print(f"  {'指标':<12}{'裸E20c':>14}{'+信号B减仓':>16}{'变化':>14}")
    print("-" * 64)

    def _row(n, a, b, pct=True):
        if pct:
            print(f"  {n:<12}{a:>13.1%}{b:>15.1%}{(b-a)*100:>+12.1f}pp")
        else:
            print(f"  {n:<12}{a:>13.2f}{b:>15.2f}{(b-a):>+13.3f}")

    _row("Sharpe", s_raw["sharpe"], s_gat["sharpe"], pct=False)
    _row("MaxDD", s_raw["max_dd"], s_gat["max_dd"])
    _row("Calmar", s_raw["calmar"], s_gat["calmar"], pct=False)
    _row("CAGR", s_raw["cagr"], s_gat["cagr"])
    _row("TotalRet", s_raw["total"], s_gat["total"])
    print("-" * 64)

    dd_imp = (abs(s_raw["max_dd"]) - abs(s_gat["max_dd"])) / abs(s_raw["max_dd"]) if s_raw["max_dd"] else 0
    sharpe_ok = s_gat["sharpe"] >= s_raw["sharpe"] - 1e-9
    print(f"  MaxDD改善: {dd_imp:+.1%} (门槛≥+10%) | Sharpe不劣化: {'✅' if sharpe_ok else '❌'}")
    print(f"  判定: {'✅ 通过' if (dd_imp >= 0.10 and sharpe_ok) else '❌ 未达门槛'}")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()
