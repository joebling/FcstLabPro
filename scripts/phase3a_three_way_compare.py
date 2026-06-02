#!/usr/bin/env python3
"""Phase 3a: 三策略对比 — 验证"信号B 当第一道软刹车 + 线上熔断兜底"互补假说.

三个策略 (含顶 OOS, init_train=250):
  S1 裸 E20c              : 纯模型信号, 无 regime
  S2 E20c + 线上熔断       : 当前线上做法 (63天滚动收益≤-10% → 清仓静默)
  S3 E20c + 线上熔断 + 信号B : 叠加 (信号B顶部软减仓在前, 线上熔断兜底在后)

核心问题: S3 vs S2 — 加上信号B 的"事前软减仓"能否进一步改善回撤?

防未来函数: 价格熔断用 iloc 回看; MVRV-Z shift(1).

用法:
    .venv/bin/python scripts/phase3a_three_way_compare.py
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
    ap.add_argument("--init-train", type=int, default=250)
    ap.add_argument("--hold-days", type=int, default=63, help="信号B减仓持续天数")
    ap.add_argument("--cut-mult", type=float, default=0.3, help="信号B减仓乘子")
    ap.add_argument("--bear-window", type=int, default=63, help="线上熔断回看窗口")
    ap.add_argument("--bear-thr", type=float, default=-0.10, help="线上熔断阈值")
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
    px = close.reindex(oos.index)

    # ---- 线上熔断: 63天滚动收益 ≤ -10% (复刻 live_signal.is_bear_market) ----
    w = args.bear_window
    roll_ret = px / px.shift(w) - 1
    bear = (roll_ret <= args.bear_thr).fillna(False)  # True = 熊市 → 清仓

    # ---- 信号B: MVRV-Z 90日动量转负, 触发后 hold 天减仓 ----
    mvrv = pd.read_csv("data/external/onchain/mvrv_zscore_data.csv",
                       parse_dates=["date"]).set_index("date")["value"]
    m1 = mvrv.shift(1)
    mom90 = m1 - m1.rolling(90).mean()
    sigB = ((mom90 < -0.2) & (mom90.shift(10) > 0)).reindex(oos.index, method="ffill").fillna(False)
    cutB = pd.Series(1.0, index=oos.index)
    for ti in np.where(sigB.values)[0]:
        cutB.iloc[ti: ti + args.hold_days] = args.cut_mult

    ret = px.pct_change().shift(-1)
    base_pos = oos["pred"].astype(float)

    # 三策略仓位
    pos_s1 = base_pos                                          # 裸
    pos_s2 = base_pos * (~bear).astype(float).values          # +线上熔断
    pos_s3 = base_pos * (~bear).astype(float).values * cutB.values  # +熔断+信号B

    def _r(pos):
        pos = pd.Series(pos, index=oos.index)
        tr = pos.diff().abs().fillna(pos.abs())
        return (pos * ret - tr * args.cost).values

    s = {n: _stats(_r(p)) for n, p in
         [("S1 裸E20c", pos_s1), ("S2 +线上熔断", pos_s2), ("S3 +熔断+信号B", pos_s3)]}

    bear_days = int(bear.sum())
    cut_days = int((cutB < 1.0).sum())
    print("\n" + "=" * 72)
    print("  Phase 3a 三策略对比 (含顶 OOS) — 验证'信号B软刹车+线上熔断兜底'")
    print("=" * 72)
    print(f"  OOS: {oos.index[0].date()}~{oos.index[-1].date()} ({len(oos)}天)")
    print(f"  线上熔断({args.bear_window}天≤{args.bear_thr:.0%}): {bear_days}天清仓 | "
          f"信号B减仓({args.cut_mult:.0%},{args.hold_days}天): {cut_days}天")
    print("-" * 72)
    print(f"  {'指标':<10}{'S1 裸':>14}{'S2 +熔断':>16}{'S3 +熔断+B':>16}")
    print("-" * 72)
    for key, name, pct in [("sharpe", "Sharpe", False), ("max_dd", "MaxDD", True),
                            ("calmar", "Calmar", False), ("cagr", "CAGR", True),
                            ("total", "TotalRet", True)]:
        a, b, c = s["S1 裸E20c"][key], s["S2 +线上熔断"][key], s["S3 +熔断+信号B"][key]
        if pct:
            print(f"  {name:<10}{a:>13.1%}{b:>15.1%}{c:>15.1%}")
        else:
            print(f"  {name:<10}{a:>13.2f}{b:>15.2f}{c:>15.2f}")
    print("-" * 72)

    # S3 vs S2 增量判定
    dd2, dd3 = abs(s["S2 +线上熔断"]["max_dd"]), abs(s["S3 +熔断+信号B"]["max_dd"])
    dd_imp = (dd2 - dd3) / dd2 if dd2 else 0
    sh2, sh3 = s["S2 +线上熔断"]["sharpe"], s["S3 +熔断+信号B"]["sharpe"]
    print(f"  ★ S3 vs S2 (信号B 增量价值):")
    print(f"     MaxDD: {dd2:.1%}→{dd3:.1%} (改善 {dd_imp:+.1%})")
    print(f"     Sharpe: {sh2:.2f}→{sh3:.2f} ({sh3-sh2:+.2f})")
    verdict = "✅ 信号B 在熔断之上仍有增量" if (dd_imp >= 0.05 and sh3 >= sh2 - 1e-9) else \
              "⚠️ 信号B 增量有限/被熔断覆盖"
    print(f"     判定: {verdict}")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()
