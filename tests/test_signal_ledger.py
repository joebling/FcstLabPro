"""测试 src/serving/signal_ledger.py —— 信号账本 + 监控产物.

覆盖:
  1. live 模式 → 写 live + archive
  2. shadow 模式 → 只写 archive (不动 live)
  3. dry-run → 不落盘
  4. 非法 mode → ValueError
  5. provenance 戳完整 (model/hash/variant/input_data_end/sha)
  6. archive 多版本可共存
  7. write_monitoring 产物结构
"""
from __future__ import annotations

import json

import pytest

import src.serving.signal_ledger as ledger


@pytest.fixture(autouse=True)
def _redirect_dirs(tmp_path, monkeypatch):
    """把账本/监控目录重定向到临时目录, 避免污染真实 data/."""
    monkeypatch.setattr(ledger, "SIGNALS_DIR", tmp_path / "signals")
    monkeypatch.setattr(ledger, "MONITORING_DIR", tmp_path / "monitoring")
    monkeypatch.setattr(ledger, "PROJECT_ROOT", tmp_path)
    return tmp_path


def _payload():
    return {"date": "2026-05-29", "signal": "BUY", "price": 73428.94}


def _kwargs(mode="live"):
    return dict(
        model_name="e1-conservative",
        model_hash="4ca65e75f1df1b72",
        variant="conservative",
        input_data_end="2026-05-28",
        mode=mode,
        feature_cols_sha256="761edbd4b124",
    )


def test_live_writes_both(tmp_path):
    written = ledger.record_signal(_payload(), **_kwargs("live"))
    assert "live" in written and "archive" in written
    assert written["live"].exists()
    assert written["archive"].exists()

    live_doc = json.loads(written["live"].read_text())
    assert live_doc["score_source"] == "live"
    assert live_doc["signal"] == "BUY"


def test_shadow_writes_archive_only(tmp_path):
    written = ledger.record_signal(_payload(), **_kwargs("shadow"))
    assert "archive" in written
    assert "live" not in written  # shadow 不动 live

    doc = json.loads(written["archive"].read_text())
    assert doc["score_source"] == "shadow"


def test_dry_run_writes_nothing():
    written = ledger.record_signal(_payload(), **_kwargs("dry-run"))
    assert written == {}


def test_unknown_mode_raises():
    with pytest.raises(ValueError, match="未知 mode"):
        ledger.record_signal(_payload(), **{**_kwargs(), "mode": "yolo"})


def test_provenance_complete():
    written = ledger.record_signal(_payload(), **_kwargs("live"))
    prov = json.loads(written["live"].read_text())["provenance"]
    assert prov["model_name"] == "e1-conservative"
    assert prov["model_hash"] == "4ca65e75f1df1b72"
    assert prov["strategy_variant"] == "conservative"
    assert prov["input_data_end"] == "2026-05-28"
    assert prov["feature_cols_sha256"] == "761edbd4b124"
    assert "generated_at" in prov


def test_archive_keeps_multiple_versions():
    ledger.record_signal({"date": "2026-05-28", "signal": "HOLD"}, **_kwargs("live"))
    ledger.record_signal({"date": "2026-05-29", "signal": "BUY"}, **_kwargs("live"))
    archive_dir = ledger.SIGNALS_DIR / "archive" / "e1-conservative"
    files = sorted(p.name for p in archive_dir.glob("*.json"))
    assert files == ["2026-05-28.json", "2026-05-29.json"]


def test_write_monitoring():
    out = ledger.write_monitoring(
        model_name="e1-conservative", n_rows=2141,
        data_last_date="2026-05-28", signal="SILENT",
        probability=0.42,
    )
    assert out.exists()
    doc = json.loads(out.read_text())
    assert doc["n_rows"] == 2141
    assert doc["signal"] == "SILENT"
    assert doc["probability"] == 0.42
