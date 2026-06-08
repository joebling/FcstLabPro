"""特征契约 — 训推一致性的唯一守门员.

把原本埋在 scripts/live_signal.py 里的特征构建 + 列序校验逻辑抽到这里,
让训练侧 (runner) 和推理侧 (live_signal) 共用同一份契约, 消除漂移风险。
对应 docs/reviews/cr_0529 §3。

核心保证: model.joblib (LightGBM) 内部只记 Column_0..N 占位符, 推理时
不会按名重排。若 train↔serve 列序静默变动, 推理会拿错输入却不报错。
feature_cols.json + validate_feature_cols() 是唯一可靠闸门。

⚠️ 本模块逻辑从 live_signal.py 原样搬迁, 不改任何数值行为 (保 bit-exact)。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def build_feature_frame(
    df: pd.DataFrame, config: dict
) -> tuple[pd.DataFrame, list[str]]:
    """按 config 构建特征, 返回 (df, feature_cols).

    训练 (runner) 与推理 (live_signal) 都应走这里, 保证列定义一致。
    """
    from src.features.builder import build_features, get_feature_columns

    feat_cfg = config["features"]
    df = build_features(
        df,
        feature_sets=feat_cfg["sets"],
        drop_na_method=feat_cfg.get("drop_na_method", "ffill_then_drop"),
        drop_features=feat_cfg.get("drop_features"),
    )
    feature_cols = get_feature_columns(df)
    return df, feature_cols


def validate_feature_cols(feature_cols: list[str], model_path: Path) -> None:
    """校验推理列序与训练时 feature_cols.json 逐位一致.

    Parameters
    ----------
    feature_cols : 本次推理的列顺序 (来自 get_feature_columns)
    model_path : model.joblib 路径, 同目录期望有 feature_cols.json

    Raises
    ------
    ValueError : feature_cols.json 存在但与本次推理不一致时。
    """
    fc_path = model_path.parent / "feature_cols.json"
    if not fc_path.exists():
        logger.warning(
            "⚠️  %s 不存在 — 跳过列序校验。老模型未随带此文件，"
            "推理与训练的列对齐仅靠「`build_features` 输出顺序未变」的默契。"
            "请在下次 promote 时生成该文件。详见 docs/specs/data_pipeline.md §10。",
            fc_path,
        )
        return

    with open(fc_path) as f:
        doc = json.load(f)
    expected = doc.get("feature_cols", [])

    if len(feature_cols) != len(expected):
        raise ValueError(
            f"特征数量不匹配: 训练时 {len(expected)} 列, 推理时 {len(feature_cols)} 列. "
            f"有人改了 src/features/* 但未重新 promote? 参考 {fc_path}"
        )

    if list(feature_cols) != list(expected):
        diffs = [
            (i, e, a)
            for i, (e, a) in enumerate(zip(expected, feature_cols))
            if e != a
        ]
        preview = "; ".join(
            f"index {i}: expected={e!r}, actual={a!r}" for i, e, a in diffs[:3]
        )
        raise ValueError(
            f"特征顺序不匹配 (共 {len(diffs)} 处不同). "
            f"前 3 处: {preview}. "
            f"训练时快照: {fc_path}"
        )

    logger.info(
        "✅ 特征列序校验通过 (%d 列, sha256=%s)",
        len(feature_cols), doc.get("sha256", "")[:12],
    )
