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


# ---------------------------------------------------------------------------
# lesson_0609: partial bar drop in freshness gate
# ---------------------------------------------------------------------------

from datetime import datetime, timezone  # noqa: E402


def _now_utc(date_str: str) -> datetime:
    return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)


def test_ohlcv_drops_partial_bar_before_stale_calc(tmp_path):
    """csv 末尾是 UTC 今日 partial bar - 应剔除后再算 stale.

    事故场景再现: cron @ UTC 00:10 拉到 6/9 partial.
    升级前: stale = 0 (用 6/9 partial), 假新鲜
    升级后: stale = 1 (用 6/8 完整), 真实
    """
    p = tmp_path / "ohlcv.csv"
    _write_ohlcv(p, last_date="2026-06-09", days=14)  # 末尾 6/9
    report = check_ohlcv_freshness(
        ohlcv_path=p, sla_days=2, now_utc=_now_utc("2026-06-09 00:10"),
    )
    assert report.ok
    assert report.stale_days == 1, "应该按 6/8 算 stale (1 天), 而非 6/9 partial (0 天)"
    assert "partial bar" in report.detail
    assert "2026-06-09" in report.detail  # 被剔除的日期写入 detail


def test_ohlcv_partial_bar_does_not_mask_real_staleness(tmp_path):
    """csv 末尾是今日 partial, 但前一行也太老 - 应 FATAL 而非被 partial 救场.

    防御场景: 下载只补到了今日 partial 但 T-1/T-2 数据其实没拉到.
    """
    # 末尾 14 行: 2026-05-26 ~ 2026-06-09 - drop partial 后 last=6/8, stale=1, OK
    # 改造: 只写 2026-06-09 (partial) + 2026-05-01 (一个老数据) - drop 后 last=5/1, stale=39, FATAL
    p = tmp_path / "ohlcv.csv"
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-05-01", "2026-06-09"]),
        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0,
    })
    df.to_csv(p, index=False)
    with pytest.raises(DataFreshnessError, match=r"过期"):
        check_ohlcv_freshness(
            ohlcv_path=p, sla_days=2, now_utc=_now_utc("2026-06-09 00:10"),
        )


def test_ohlcv_only_partial_bar_fatal(tmp_path):
    """csv 仅含 partial bar (drop 后空) - 应 FATAL, 不能裸奔."""
    p = tmp_path / "ohlcv.csv"
    df = pd.DataFrame({
        "date": [pd.Timestamp("2026-06-09")],
        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0,
    })
    df.to_csv(p, index=False)
    with pytest.raises(DataFreshnessError, match=r"partial bar"):
        check_ohlcv_freshness(
            ohlcv_path=p, sla_days=2, now_utc=_now_utc("2026-06-09 00:10"),
        )


def test_ohlcv_yesterday_last_bar_unchanged(tmp_path):
    """csv 末尾是 T-1 完整 bar (非 partial) - 不应该被 drop."""
    p = tmp_path / "ohlcv.csv"
    _write_ohlcv(p, last_date="2026-06-08", days=14)  # 末尾 6/8 (相对 today=6/9)
    report = check_ohlcv_freshness(
        ohlcv_path=p, sla_days=2, now_utc=_now_utc("2026-06-09 00:10"),
    )
    assert report.ok
    assert report.stale_days == 1
    assert "partial bar" not in report.detail  # 没 drop, detail 里不带这词
