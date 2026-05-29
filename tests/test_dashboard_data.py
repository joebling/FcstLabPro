"""Dashboard 数据层测试 — signals / market / models 容错 + 结构.

重点: 文件缺失/损坏不崩, 返回结构稳定 (前端模板依赖这些 key)。
"""
from __future__ import annotations

import json

from src.dashboard.data import signals, market, models


# ---------- signals ----------

def test_latest_signal_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(signals, "ARCHIVE_DIR", tmp_path)
    assert signals.latest_signal("nope") is None


def test_signal_history_and_dist(monkeypatch, tmp_path):
    monkeypatch.setattr(signals, "ARCHIVE_DIR", tmp_path)
    mdir = tmp_path / "m1"
    mdir.mkdir()
    for d, sig in [("2026-01-01", "BUY"), ("2026-01-02", "SILENT"), ("2026-01-03", "BUY")]:
        (mdir / f"{d}.json").write_text(json.dumps(
            {"date": d, "signal": sig, "price": 100.0, "regime": "牛市"}))
    hist = signals.signal_history("m1")
    assert hist[0]["date"] == "2026-01-03"   # 倒序
    assert signals.signal_distribution("m1") == {"BUY": 2, "SILENT": 1}


def test_signal_calendar(monkeypatch, tmp_path):
    monkeypatch.setattr(signals, "ARCHIVE_DIR", tmp_path)
    mdir = tmp_path / "m1"
    mdir.mkdir()
    (mdir / "2026-03-15.json").write_text(json.dumps(
        {"date": "2026-03-15", "signal": "BUY", "price": 100.0, "regime": "牛市"}))
    (mdir / "2026-04-01.json").write_text(json.dumps(
        {"date": "2026-04-01", "signal": "SILENT", "price": 90.0, "regime": "熊市"}))
    cal = signals.signal_calendar("m1", 2026, 3)
    assert "2026-03-15" in cal
    assert "2026-04-01" not in cal     # 不同月


def test_corrupt_signal_skipped(monkeypatch, tmp_path):
    monkeypatch.setattr(signals, "ARCHIVE_DIR", tmp_path)
    mdir = tmp_path / "m1"
    mdir.mkdir()
    (mdir / "2026-01-01.json").write_text("{ broken")
    assert signals.signal_history("m1") == []


# ---------- market ----------

def test_market_series_structure():
    """真实数据: 关键 key 必须在 (模板依赖)."""
    p = market.price_series(days=30)
    assert set(p) >= {"dates", "close", "volume"}
    f = market.fgi_series(days=30)
    assert set(f) >= {"dates", "series", "latest_class", "latest_value"}
    assert isinstance(market.macro_series(), dict)


def test_market_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(market, "EXTERNAL_DIR", tmp_path)
    assert market.funding_series() == {"dates": [], "series": []}


# ---------- models ----------

def test_active_models_structure():
    ms = models.active_models()
    assert len(ms) >= 1
    m = ms[0]
    for k in ("slot", "name", "role", "status", "model_hash", "metrics", "pnl_metrics"):
        assert k in m


def test_freshness_gate():
    fg = models.freshness_gate()
    assert isinstance(fg, dict)   # 真实 active.yaml 有 data_freshness
