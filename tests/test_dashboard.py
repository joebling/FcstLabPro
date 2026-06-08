"""Dashboard V2 路由烟测 — 4 页渲染 + 容错.

纯展示层, 重点: 4 页都能渲染 + 数据异常不崩。
数据层细节在 test_dashboard_data.py, performance 在 test_performance.py。
"""
from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")


@pytest.fixture
def client(monkeypatch):
    from starlette.testclient import TestClient
    from src.dashboard.app import app
    return TestClient(app)


def test_overview_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "📊 总览" in r.text
    assert "priceChart" in r.text         # 价格图 canvas


def test_signals_renders(client):
    r = client.get("/signals")
    assert r.status_code == 200
    assert "📡 信号" in r.text
    assert "信号实现明细" in r.text


def test_market_renders(client):
    r = client.get("/market")
    assert r.status_code == 200
    assert "📈 市场" in r.text
    assert "恐惧贪婪指数" in r.text
    assert "mktFunding" in r.text          # 资金费率图


def test_models_renders(client):
    r = client.get("/models")
    assert r.status_code == 200
    assert "🤖 模型" in r.text
    assert "e1-conservative" in r.text
    assert "数据新鲜度门" in r.text


def test_sidebar_nav_present(client):
    """侧边栏 6 个导航项都在."""
    r = client.get("/")
    for label in ("总览", "信号", "市场", "顶部", "实盘", "模型"):
        assert label in r.text


def test_perfmon_renders(client):
    """实盘业绩页: 渲染 + 无账本不崩 (本地无 state 优雅降级)."""
    r = client.get("/perfmon")
    assert r.status_code == 200
    assert "实盘业绩监控" in r.text


def test_topping_renders(client):
    """顶部页: 三层危险分级 + 历史回放图."""
    r = client.get("/topping")
    assert r.status_code == 200
    assert "顶部研判" in r.text
    assert "当前危险等级" in r.text
    assert "Layer A" in r.text
    assert "topHist" in r.text             # 历史点灯回放 canvas


def test_model_switch_query(client):
    """?model= 切换不崩 (全页刷新模式)."""
    r = client.get("/?model=e8-touch")
    assert r.status_code == 200
