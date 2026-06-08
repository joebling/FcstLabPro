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
    fs = market.funding_series()
    assert fs["dates"] == [] and fs["series"] == []
    # 缺文件 → 标记陈旧 (新鲜度纵深防御)
    assert fs["stale"] is True and fs["as_of"] is None


def test_market_freshness_keys():
    """每个 series 必带 as_of/age_days/stale (模板新鲜度徽章依赖)."""
    for s in (market.funding_series(), market.taker_ratio_series(),
              market.open_interest_series(), market.price_series(),
              market.fgi_series(), market.macro_series()):
        assert {"as_of", "age_days", "stale"} <= set(s)


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


# ---------- ledger (生产持仓账本) ----------

def test_ledger_missing_state_graceful(monkeypatch, tmp_path):
    """无 state 文件 → 返回稳定空结构, 不崩."""
    from src.dashboard.data import ledger
    monkeypatch.setattr(ledger, "STATE_DIR", tmp_path)
    pos = ledger.position("nope")
    assert pos["has_state"] is False and pos["in_position"] is False
    assert ledger.trade_history("nope")["total_trades"] == 0


def test_ledger_reads_real_trades(monkeypatch, tmp_path):
    """读真实 state → 持仓/regime/战绩与邮件同源 (复用 _parse_history)."""
    from src.dashboard.data import ledger
    monkeypatch.setattr(ledger, "STATE_DIR", tmp_path)
    (tmp_path / "m_state.json").write_text(json.dumps({
        "in_position": False, "last_signal": "SELL", "last_regime": "熊市",
        "last_reason": "regime=熊市, 强制平仓", "last_regime_detail": "63d=-11.8%",
        "history": [{"entry_date": "2026-06-05", "exit_date": "2026-06-07",
                     "entry_price": 63200.0, "exit_price": 60865.64,
                     "pnl": -0.037, "days_held": 2, "reason": "regime=熊市, 强制平仓"}],
    }, ensure_ascii=False))
    pos = ledger.position("m")
    assert pos["last_signal"] == "SELL" and pos["regime"] == "熊市"
    h = ledger.trade_history("m")
    assert h["total_trades"] == 1 and h["win_rate"] == 0.0
    assert h["recent"][0]["pnl"] == "-3.7%"


# ---------- perfmon (实盘业绩监控) ----------

def test_perfmon_equity_drawdown_and_gating(monkeypatch, tmp_path):
    """净值曲线/回撤/样本量 gating 正确."""
    from src.dashboard.data import ledger, perfmon
    monkeypatch.setattr(ledger, "STATE_DIR", tmp_path)
    (tmp_path / "m_state.json").write_text(json.dumps({
        "history": [
            {"exit_date": "2026-03-22", "pnl": 0.05, "reason": "到期: T=21"},
            {"exit_date": "2026-04-15", "pnl": -0.03, "reason": "到期: T=21"},
            {"exit_date": "2026-06-07", "pnl": -0.037, "reason": "regime=熊市, 强制平仓"},
        ],
    }, ensure_ascii=False))
    c = perfmon.build("m", "conservative")
    assert c["n_trades"] == 3
    assert c["sample_ok"] is False           # n<20 → gated
    assert len(c["curve"]["equity"]) == 3
    assert c["max_drawdown"] <= 0
    # 净值 = 1.05 * 0.97 * 0.963 ≈ 0.9806
    assert abs(c["total_return"] - (1.05 * 0.97 * 0.963 - 1)) < 1e-3


def test_perfmon_no_state_graceful(monkeypatch, tmp_path):
    from src.dashboard.data import ledger, perfmon
    monkeypatch.setattr(ledger, "STATE_DIR", tmp_path)
    c = perfmon.build("nope", "conservative")
    assert c["has_state"] is False and c["n_trades"] == 0
