"""Dashboard 测试 — data_access schema 锁定 + 路由烟测.

dashboard 是纯展示层, 测试重点: 读坏数据不崩 + 关键 UI 元素在。
"""
from __future__ import annotations

import json
import warnings

import pytest

warnings.filterwarnings("ignore")


# ---------- data_access 容错 ----------

def test_load_batches_no_data(tmp_path, monkeypatch):
    import src.dashboard.config as cfg
    import src.dashboard.data_access as da
    monkeypatch.setattr(cfg, "PERF_DIR", tmp_path)
    monkeypatch.setattr(da, "PERF_DIR", tmp_path)
    out = da.load_batches("nonexistent")
    assert out["rows"] == []
    assert out["stale"] is True
    assert out["reason"] == "no_data"


def test_load_batches_corrupt(tmp_path, monkeypatch):
    import src.dashboard.data_access as da
    monkeypatch.setattr(da, "PERF_DIR", tmp_path)
    mdir = tmp_path / "m1"
    mdir.mkdir()
    (mdir / "batches.json").write_text("{ not valid json")
    out = da.load_batches("m1")
    assert out["rows"] == []
    assert out["reason"] == "corrupt"


def test_load_batches_ok(tmp_path, monkeypatch):
    import src.dashboard.data_access as da
    monkeypatch.setattr(da, "PERF_DIR", tmp_path)
    mdir = tmp_path / "m1"
    mdir.mkdir()
    rows = [{"score_date": "2026-01-01", "n_signals": 1, "status": "MATURE",
             "hit_rate": 100.0, "avg_realized_return": 5.0, "n_buy": 1,
             "n_silent": 0, "model_hash": "abc12345"}]
    (mdir / "batches.json").write_text(json.dumps(rows))
    out = da.load_batches("m1")
    assert out["rows"] == rows
    assert out["reason"] == "ok"


# ---------- 路由烟测 ----------

@pytest.fixture
def client(tmp_path, monkeypatch):
    """构造带合成数据的 dashboard client."""
    import src.dashboard.data_access as da
    monkeypatch.setattr(da, "PERF_DIR", tmp_path)
    for name in ("modelA", "modelB"):
        mdir = tmp_path / name
        mdir.mkdir()
        (mdir / "batches.json").write_text(json.dumps([
            {"score_date": "2026-01-01", "n_signals": 1, "n_buy": 1, "n_silent": 0,
             "status": "MATURE", "hit_rate": 100.0, "avg_realized_return": 5.0,
             "model_hash": "abc12345"},
            {"score_date": "2026-02-01", "n_signals": 1, "n_buy": 0, "n_silent": 1,
             "status": "PENDING", "hit_rate": None, "avg_realized_return": None,
             "model_hash": "abc12345"},
        ]))
        (mdir / "summary.json").write_text(json.dumps({
            "n_total": 2, "n_mature": 1, "n_pending": 1, "n_bets": 1,
            "hit_rate": 100.0, "avg_realized_return": 5.0, "rank_ic": 0.05,
        }))
    monkeypatch.setattr(da, "list_models", lambda: ["modelA", "modelB"])

    from starlette.testclient import TestClient
    from src.dashboard.app import app
    return TestClient(app)


def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Score Batch Detail" in r.text
    assert "modelA" in r.text
    assert "⏳" in r.text          # PENDING 三态


def test_partial_model_switch(client):
    r = client.get("/partial/model?model=modelB")
    assert r.status_code == 200
    assert "Score Batch Detail" in r.text
    # partial 不应含整页骨架
    assert "<html" not in r.text
