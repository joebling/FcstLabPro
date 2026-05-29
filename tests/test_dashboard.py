"""Dashboard 测试 — 实时算+缓存模式. mock service 层验证展示逻辑.

dashboard 是纯展示层, 测试重点: service 异常不崩 + 关键 UI 元素在。
"""
from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")


# ---------- data_access 容错 ----------

def test_load_batches_error_fallback(monkeypatch):
    """service 抛异常 → 不崩, 返回 error reason."""
    import src.dashboard.data_access as da

    def boom(_):
        raise RuntimeError("archive 读取失败")

    monkeypatch.setattr(da.service, "get_batches", boom)
    out = da.load_batches("m1")
    assert out["rows"] == []
    assert out["reason"] == "error"
    assert out["stale"] is True


def test_load_batches_ok(monkeypatch):
    import src.dashboard.data_access as da
    rows = [{"score_date": "2026-01-01", "n_signals": 1, "status": "MATURE",
             "hit_rate": 100.0, "avg_realized_return": 5.0, "n_buy": 1,
             "n_silent": 0, "model_hash": "abc12345"}]
    monkeypatch.setattr(da.service, "get_batches", lambda m: (rows, 1700000000.0))
    out = da.load_batches("m1")
    assert out["rows"] == rows
    assert out["reason"] == "ok"
    assert out["stale"] is False
    assert "computed_age_minutes" in out


def test_load_batches_empty(monkeypatch):
    import src.dashboard.data_access as da
    monkeypatch.setattr(da.service, "get_batches", lambda m: ([], 1700000000.0))
    out = da.load_batches("m1")
    assert out["reason"] == "no_data"
    assert out["stale"] is True


# ---------- 路由烟测 ----------

@pytest.fixture
def client(monkeypatch):
    """构造带 mock service 的 dashboard client."""
    import src.dashboard.data_access as da

    batches = [
        {"score_date": "2026-01-01", "n_signals": 1, "n_buy": 1, "n_silent": 0,
         "status": "MATURE", "hit_rate": 100.0, "avg_realized_return": 5.0,
         "model_hash": "abc12345"},
        {"score_date": "2026-02-01", "n_signals": 1, "n_buy": 0, "n_silent": 1,
         "status": "PENDING", "hit_rate": None, "avg_realized_return": None,
         "model_hash": "abc12345"},
    ]
    summary = {"n_total": 2, "n_mature": 1, "n_pending": 1, "n_bets": 1,
               "hit_rate": 100.0, "avg_realized_return": 5.0, "rank_ic": 0.05}

    monkeypatch.setattr(da, "list_models", lambda: ["modelA", "modelB"])
    monkeypatch.setattr(da.service, "get_batches", lambda m: (batches, 1700000000.0))
    monkeypatch.setattr(da.service, "get_summary", lambda m: (summary, 1700000000.0))

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
    assert "<html" not in r.text   # partial 不含整页骨架
