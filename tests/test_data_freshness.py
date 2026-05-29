"""数据新鲜度 gate 测试 — 锁死决策 A: 缺失/过期一律 FATAL.

防止以后有人手滑把 live gate 改回静默 ffill stale FGI。
对应 docs/reviews/cr_0529 §B。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.serving.data_freshness import (
    DataFreshnessError,
    check_fgi_freshness,
    check_ohlcv_freshness,
)


def _write_ohlcv(path: Path, last_date: str, days: int = 10) -> None:
    dates = pd.date_range(end=last_date, periods=days, freq="D")
    df = pd.DataFrame({
        "date": dates,
        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0,
    })
    df.to_csv(path, index=False)


def _write_fgi(path: Path, last_date: str, days: int = 10) -> None:
    dates = pd.date_range(end=last_date, periods=days, freq="D")
    df = pd.DataFrame({
        "date": dates, "fgi_value": 50, "fgi_class": "Neutral",
    })
    df.to_csv(path, index=False)


def test_ohlcv_fresh_passes(tmp_path):
    p = tmp_path / "ohlcv.csv"
    today = pd.Timestamp.utcnow().normalize()
    _write_ohlcv(p, last_date=str(today.date()))
    report = check_ohlcv_freshness(ohlcv_path=p, sla_days=2)
    assert report.ok
    assert report.stale_days <= 2


def test_ohlcv_stale_fatal(tmp_path):
    p = tmp_path / "ohlcv.csv"
    _write_ohlcv(p, last_date="2020-01-10")
    with pytest.raises(DataFreshnessError, match="OHLCV"):
        check_ohlcv_freshness(ohlcv_path=p, sla_days=2)


def test_ohlcv_missing_fatal(tmp_path):
    with pytest.raises(DataFreshnessError, match="不存在"):
        check_ohlcv_freshness(ohlcv_path=tmp_path / "nope.csv", sla_days=2)


def test_fgi_fresh_passes(tmp_path):
    ohlcv = tmp_path / "ohlcv.csv"
    fgi = tmp_path / "fgi.csv"
    _write_ohlcv(ohlcv, last_date="2026-05-28")
    _write_fgi(fgi, last_date="2026-05-27")
    report = check_fgi_freshness(fgi_path=fgi, ohlcv_path=ohlcv, sla_days=2)
    assert report.ok
    assert report.stale_days == 1


def test_fgi_stale_fatal(tmp_path):
    ohlcv = tmp_path / "ohlcv.csv"
    fgi = tmp_path / "fgi.csv"
    _write_ohlcv(ohlcv, last_date="2026-05-28")
    _write_fgi(fgi, last_date="2026-03-08")
    with pytest.raises(DataFreshnessError, match="FGI"):
        check_fgi_freshness(fgi_path=fgi, ohlcv_path=ohlcv, sla_days=2)


def test_fgi_missing_fatal(tmp_path):
    ohlcv = tmp_path / "ohlcv.csv"
    _write_ohlcv(ohlcv, last_date="2026-05-28")
    with pytest.raises(DataFreshnessError, match="不存在"):
        check_fgi_freshness(
            fgi_path=tmp_path / "nope.csv", ohlcv_path=ohlcv, sla_days=2
        )


def test_fgi_missing_value_column_fatal(tmp_path):
    ohlcv = tmp_path / "ohlcv.csv"
    fgi = tmp_path / "fgi.csv"
    _write_ohlcv(ohlcv, last_date="2026-05-28")
    pd.DataFrame({"date": pd.date_range(end="2026-05-28", periods=5)}).to_csv(
        fgi, index=False
    )
    with pytest.raises(DataFreshnessError, match="fgi_value"):
        check_fgi_freshness(fgi_path=fgi, ohlcv_path=ohlcv, sla_days=2)
