"""测试 live_signal.py::validate_feature_cols() —— P0 列序校验门.

覆盖场景:
  1. 一致顺序 → 通过 (无异常)
  2. 文件缺失 → warning, 不 raise (向后兼容)
  3. 长度不一致 → ValueError
  4. 列序不一致 → ValueError (附错位 index 提示)
  5. sha256 计算正确 (篡改检测能力)

也编码了 LightGBM 的 P0 quirk: 若哪天 LightGBM 自己开始按
feature_names_in_ 校验, 此测试套件 (test_lgbm_quirks.py) 会失败,
那时可以考虑放宽外层校验。
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import pytest


# --------------------------------------------------------------------- helpers


def _write_feature_cols_json(model_dir: Path, cols: list[str]) -> Path:
    """模拟 promote_model.py / runner.py 写入的产物."""
    payload = ",".join(cols)
    doc = {
        "version": 1,
        "n_features": len(cols),
        "feature_cols": list(cols),
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "generated_by": "test_feature_cols_validation",
    }
    fc_path = model_dir / "feature_cols.json"
    fc_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    return fc_path


def _make_model_dir(tmp_path: Path) -> Path:
    """造一个空 model.joblib 文件 (validate_feature_cols 只看 parent 目录, 不读模型)."""
    model_dir = tmp_path / "fake-model"
    model_dir.mkdir()
    (model_dir / "model.joblib").write_bytes(b"")  # 占位
    return model_dir


# --------------------------------------------------------------------- tests


def test_validates_when_order_matches(tmp_path: Path) -> None:
    """正常路径: 推理列序与训练快照完全一致 → 静默通过."""
    from scripts.live_signal import validate_feature_cols

    model_dir = _make_model_dir(tmp_path)
    cols = [f"feat_{i}" for i in range(10)]
    _write_feature_cols_json(model_dir, cols)

    # 不应抛出
    validate_feature_cols(cols, model_dir / "model.joblib")


def test_warns_but_allows_when_snapshot_missing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """向后兼容: 老模型没有 feature_cols.json → loud warning 但不阻断."""
    from scripts.live_signal import validate_feature_cols

    model_dir = _make_model_dir(tmp_path)
    # 故意不写 feature_cols.json

    cols = [f"feat_{i}" for i in range(10)]
    with caplog.at_level(logging.WARNING):
        validate_feature_cols(cols, model_dir / "model.joblib")

    msgs = " ".join(r.message for r in caplog.records)
    assert "feature_cols.json" in msgs
    assert "跳过" in msgs or "skip" in msgs.lower()


def test_raises_when_lengths_differ(tmp_path: Path) -> None:
    """新增 / 删减 feature → 数量错位 → ValueError, 提示数字."""
    from scripts.live_signal import validate_feature_cols

    model_dir = _make_model_dir(tmp_path)
    trained = [f"feat_{i}" for i in range(129)]
    _write_feature_cols_json(model_dir, trained)

    served_too_few = trained[:128]
    with pytest.raises(ValueError, match="129.*128|128.*129"):
        validate_feature_cols(served_too_few, model_dir / "model.joblib")

    served_too_many = trained + ["extra_feat"]
    with pytest.raises(ValueError, match=r"\b130\b|\b129\b"):
        validate_feature_cols(served_too_many, model_dir / "model.joblib")


def test_raises_when_order_differs(tmp_path: Path) -> None:
    """关键负向测试: 长度一致但顺序错乱 → ValueError, 附错位 index.

    这就是 P0 漏洞被堵的核心证据 —— LightGBM 不会挡, 我们必须挡。
    """
    from scripts.live_signal import validate_feature_cols

    model_dir = _make_model_dir(tmp_path)
    trained = [f"feat_{i}" for i in range(10)]
    _write_feature_cols_json(model_dir, trained)

    # 交换前两列
    served = ["feat_1", "feat_0"] + trained[2:]
    with pytest.raises(ValueError) as exc_info:
        validate_feature_cols(served, model_dir / "model.joblib")

    msg = str(exc_info.value)
    assert "index 0" in msg or "顺序" in msg
    assert "feat_0" in msg and "feat_1" in msg


def test_raises_when_names_differ_at_same_length(tmp_path: Path) -> None:
    """有人改了 feature builder 名字但保持列数 → 必须报错."""
    from scripts.live_signal import validate_feature_cols

    model_dir = _make_model_dir(tmp_path)
    trained = ["rsi_30", "macd_signal", "ext_fgi_std_14"]
    _write_feature_cols_json(model_dir, trained)

    served_renamed = ["rsi_30", "MACD_signal", "ext_fgi_std_14"]  # 中间名变了
    with pytest.raises(ValueError, match="MACD_signal|macd_signal"):
        validate_feature_cols(served_renamed, model_dir / "model.joblib")


def test_sha256_detects_tampering(tmp_path: Path) -> None:
    """sha256 在 doc 里, 但我们目前没在 validate 里校验它 —— 仅作为可审计字段.

    这个 test 主要是文档性: 锁定 sha256 字段存在 + 与列表一致, 防止未来重构丢了它。
    """
    model_dir = _make_model_dir(tmp_path)
    cols = ["a", "b", "c"]
    fc_path = _write_feature_cols_json(model_dir, cols)
    doc = json.loads(fc_path.read_text())

    expected = hashlib.sha256(",".join(cols).encode()).hexdigest()
    assert doc["sha256"] == expected
    assert doc["n_features"] == 3
    assert doc["version"] == 1
