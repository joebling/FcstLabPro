"""按 regime 拆分 E20c / E21b OOS kappa, 验证模型对牛/熊/震荡市的适用性."""
import pandas as pd
import yaml
import sys
sys.path.insert(0, '.')
from sklearn.metrics import (
    cohen_kappa_score, f1_score, precision_score, recall_score, accuracy_score
)
from src.data.loader import load_csv
from src.data.splitter import walk_forward_split
from src.features.builder import build_features
from src.labels.registry import get_label_strategy
import src.labels.directional_filtered  # noqa: F401  注册标签
import src.labels.touch_filtered  # noqa: F401
import src.features.technical  # noqa: F401  注册特征集
import src.features.volume  # noqa: F401
import src.features.flow  # noqa: F401
import src.features.market_structure  # noqa: F401
import src.features.external  # noqa: F401


def analyze(exp_dir: str, label: str):
    cfg = yaml.safe_load(open(f"{exp_dir}/config.yaml"))
    preds = pd.read_csv(f"{exp_dir}/predictions.csv")

    data_cfg = cfg["data"]
    df_raw = load_csv(
        path=data_cfg["path"],
        start=data_cfg.get("start"),
        end=data_cfg.get("end"),
        expected_sha256=data_cfg.get("expected_sha256"),
        expected_effective_rows=data_cfg.get("expected_effective_rows"),
    )
    feat_cfg = cfg["features"]
    df_feat = build_features(
        df_raw,
        feature_sets=feat_cfg["sets"],
        drop_features=feat_cfg.get("drop_features"),
        smoothing=feat_cfg.get("smoothing"),
    )
    lbl_cfg = cfg["label"]
    label_fn = get_label_strategy(lbl_cfg["strategy"])
    label_params = {k: v for k, v in lbl_cfg.items() if k != "strategy"}
    y_full = label_fn(df_feat, **label_params)

    valid_idx = y_full.dropna().index
    df_aligned = df_feat.loc[valid_idx]
    n = len(df_aligned)
    cv_cfg = cfg["evaluation"]
    folds = walk_forward_split(
        n, cv_cfg["init_train"], cv_cfg["oos_window"], cv_cfg["step"]
    )

    test_dates = []
    for fold in folds:
        for idx in range(fold.test_start, fold.test_end):
            test_dates.append(df_aligned.index[idx])

    assert len(test_dates) == len(preds), (
        f"date {len(test_dates)} vs pred {len(preds)}"
    )
    preds["date"] = test_dates
    preds = preds.set_index("date")

    btc = df_raw[["close"]].copy()
    btc["ma_200"] = btc["close"].rolling(200).mean()
    btc["regime"] = "sideways"
    bull_mask = (btc["close"] > btc["ma_200"]) & (btc["ma_200"].diff(20) > 0)
    bear_mask = (btc["close"] < btc["ma_200"]) & (btc["ma_200"].diff(20) < 0)
    btc.loc[bull_mask, "regime"] = "bull"
    btc.loc[bear_mask, "regime"] = "bear"
    preds["regime"] = btc.reindex(preds.index)["regime"]

    print(f"\n═══ {label} ═══")
    print(
        f"OOS: {preds.index.min().date()} ~ {preds.index.max().date()} "
        f"| n={len(preds)}"
    )
    header = (
        f"{'regime':<10} {'n':>5} {'kappa':>8} {'acc':>7} {'f1':>7} "
        f"{'prec':>7} {'recall':>7} {'pos_true':>9} {'pos_pred':>9}"
    )
    print(header)
    print("-" * 82)
    for regime in ["bull", "bear", "sideways", "ALL"]:
        sub = preds if regime == "ALL" else preds[preds["regime"] == regime]
        if len(sub) < 5:
            continue
        y_t, y_p = sub["y_true"].values, sub["y_pred"].values
        kp = (
            cohen_kappa_score(y_t, y_p)
            if (y_t.sum() + y_p.sum()) > 0
            else 0.0
        )
        ac = accuracy_score(y_t, y_p)
        f1 = f1_score(y_t, y_p, zero_division=0)
        pr = precision_score(y_t, y_p, zero_division=0)
        rc = recall_score(y_t, y_p, zero_division=0)
        marker = " 🌟" if regime == "ALL" else ""
        print(
            f"{regime:<10} {len(sub):>5} {kp:>8.4f} {ac:>7.4f} {f1:>7.4f} "
            f"{pr:>7.4f} {rc:>7.4f} {y_t.mean():>8.1%} {y_p.mean():>8.1%}"
            f"{marker}"
        )


if __name__ == "__main__":
    analyze(
        "experiments/weekly/v0601_E20c_prune_core_run1",
        "E20c (E1 系, directional, 28 feat)",
    )
    analyze(
        "experiments/weekly/v0601_E21b_prune_weak_run1",
        "E21b (E8 系, touch, 81 feat)",
    )
