#!/usr/bin/env python3
"""严格去重版 regime Kappa 验证 (纯研究, 不碰生产).

修正 analyze_regime_kappa.py 的方法论瑕疵:
  原脚本在重叠 walk-forward 预测 (oos_window=63, step=21 -> 2.89x 重复) 上
  直接按 regime 拆分算 kappa, 同一日期被计入 ~3 次, 可能扭曲 regime 权重。

本脚本: 每个日期只保留第一次(最早 fold) 的预测, 去重后重新按 regime 算 kappa,
验证「e20c 牛市/震荡强、熊市弱」结论是否稳健。

用法:
    python scripts/research/regime_kappa_dedup.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml
from sklearn.metrics import (
    accuracy_score,
    cohen_kappa_score,
    f1_score,
    precision_score,
    recall_score,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.loader import load_csv  # noqa: E402
from src.data.splitter import walk_forward_split  # noqa: E402
from src.features.builder import build_features  # noqa: E402
from src.labels.registry import get_label_strategy  # noqa: E402
import src.labels.directional_filtered  # noqa: E402,F401
import src.features.technical  # noqa: E402,F401
import src.features.volume  # noqa: E402,F401
import src.features.flow  # noqa: E402,F401
import src.features.market_structure  # noqa: E402,F401
import src.features.external  # noqa: E402,F401


def regime_table(preds, title):
    print(f"\n=== {title} ===")
    print(f"OOS: {preds.index.min().date()} ~ {preds.index.max().date()} | n={len(preds)}")
    print(f"{'regime':<10}{'n':>6}{'kappa':>9}{'acc':>8}{'f1':>8}"
          f"{'prec':>8}{'recall':>8}{'pos_true':>10}{'pos_pred':>10}")
    print("-" * 84)
    rows = []
    for regime in ["bull", "bear", "sideways", "ALL"]:
        sub = preds if regime == "ALL" else preds[preds["regime"] == regime]
        if len(sub) < 5:
            continue
        yt, yp = sub["y_true"].values, sub["y_pred"].values
        kp = cohen_kappa_score(yt, yp) if (yt.sum() + yp.sum()) > 0 else 0.0
        marker = " *" if regime == "ALL" else ""
        print(f"{regime:<10}{len(sub):>6}{kp:>9.4f}{accuracy_score(yt, yp):>8.4f}"
              f"{f1_score(yt, yp, zero_division=0):>8.4f}"
              f"{precision_score(yt, yp, zero_division=0):>8.4f}"
              f"{recall_score(yt, yp, zero_division=0):>8.4f}"
              f"{yt.mean():>9.1%}{yp.mean():>9.1%}{marker}")
        rows.append({"regime": regime, "n": len(sub), "kappa": round(kp, 4)})
    return pd.DataFrame(rows)


def build_preds_with_dates(exp_dir):
    """重建 predictions + 日期 + regime 标注 (复刻原脚本逻辑)."""
    p = PROJECT_ROOT / exp_dir
    cfg = yaml.safe_load(open(p / "config.yaml"))
    preds = pd.read_csv(p / "predictions.csv")

    dc = cfg["data"]
    df_raw = load_csv(path=dc["path"], start=dc.get("start"), end=dc.get("end"))
    fc = cfg["features"]
    df_feat = build_features(df_raw, feature_sets=fc["sets"],
                             drop_features=fc.get("drop_features"),
                             smoothing=fc.get("smoothing"))
    lc = cfg["label"]
    y_full = get_label_strategy(lc["strategy"])(
        df_feat, **{k: v for k, v in lc.items() if k != "strategy"})
    valid_idx = y_full.dropna().index
    df_aligned = df_feat.loc[valid_idx]

    ev = cfg["evaluation"]
    folds = walk_forward_split(len(df_aligned), ev["init_train"],
                               ev["oos_window"], ev["step"])
    test_dates = []
    for fold in folds:
        for idx in range(fold.test_start, fold.test_end):
            test_dates.append(df_aligned.index[idx])
    assert len(test_dates) == len(preds), f"{len(test_dates)} vs {len(preds)}"
    preds["date"] = test_dates

    # regime 标注 (200日均线 + 20日斜率)
    btc = df_raw[["close"]].copy()
    btc["ma_200"] = btc["close"].rolling(200).mean()
    btc["regime"] = "sideways"
    btc.loc[(btc["close"] > btc["ma_200"]) & (btc["ma_200"].diff(20) > 0), "regime"] = "bull"
    btc.loc[(btc["close"] < btc["ma_200"]) & (btc["ma_200"].diff(20) < 0), "regime"] = "bear"
    preds["regime"] = btc.reindex(pd.DatetimeIndex(preds["date"]))["regime"].values
    return preds


def analyze(exp_dir, label):
    preds = build_preds_with_dates(exp_dir)
    dup = len(preds) / preds["date"].nunique()

    print("\n" + "#" * 84)
    print(f"# {label}")
    print(f"# 原始预测: {len(preds)} 行 / {preds['date'].nunique()} 唯一日期 = {dup:.2f}x 重复")
    print("#" * 84)

    # 版本 A: 原始 (重叠)
    pa = preds.set_index("date")
    ta = regime_table(pa, "版本A: 原始 (重叠 walk-forward, 同日重复 ~3 次)")

    # 版本 B: 去重 (每日期保留首次预测 = 最早 fold)
    pb = preds.drop_duplicates(subset="date", keep="first").set_index("date")
    tb = regime_table(pb, "版本B: 去重 (每日期仅首次, 非重叠)")

    # 对比
    print("\n" + "=" * 84)
    print(f"【{label}】稳健性: 重叠 vs 去重 的 regime kappa")
    print("=" * 84)
    merged = ta.merge(tb, on="regime", suffixes=("_dup", "_dedup"))
    for _, r in merged.iterrows():
        delta = r["kappa_dedup"] - r["kappa_dup"]
        print(f"  {r['regime']:<10} 重叠={r['kappa_dup']:>7.4f}  "
              f"去重={r['kappa_dedup']:>7.4f}  Δ={delta:>+7.4f}")


if __name__ == "__main__":
    analyze("experiments/weekly/v0601_E20c_prune_core_run1",
            "E20c (directional, 28 feat)")
