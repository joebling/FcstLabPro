"""Test _drop_incomplete_tail_bar - lesson_0609 \u4e0b\u8f7d\u4fa7\u53cc\u4fdd\u9669."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from src.data.downloader import _drop_incomplete_tail_bar


def _mk_df(dates: list[str]) -> pd.DataFrame:
    idx = pd.to_datetime(dates)
    return pd.DataFrame({"close": list(range(len(dates)))}, index=idx)


def _now(date_str: str) -> datetime:
    return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)


class TestDropIncomplete1d:
    def test_drops_today_open_bar(self):
        df = _mk_df(["2026-06-07", "2026-06-08", "2026-06-09"])
        out = _drop_incomplete_tail_bar(df, "1d", now_utc=_now("2026-06-09 00:10"))
        assert len(out) == 2
        assert out.index[-1].date().isoformat() == "2026-06-08"

    def test_keeps_yesterday_complete_bar(self):
        df = _mk_df(["2026-06-07", "2026-06-08"])
        out = _drop_incomplete_tail_bar(df, "1d", now_utc=_now("2026-06-09 00:10"))
        assert len(out) == 2  # \u4e0d\u52a8
        assert out.index[-1].date().isoformat() == "2026-06-08"

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame({"close": []}, index=pd.DatetimeIndex([], name="date"))
        out = _drop_incomplete_tail_bar(df, "1d", now_utc=_now("2026-06-09 00:10"))
        assert out.empty


class TestDropIncomplete1w:
    def test_drops_current_week_bar(self):
        """\u672c\u5468\u5468\u4e00 open \u7684 bar (\u672a\u95ed\u5408) - \u5e94 drop."""
        # 2026-06-09 \u662f\u5468\u4e8c, \u672c\u5468\u5468\u4e00 = 2026-06-08
        df = _mk_df(["2026-05-25", "2026-06-01", "2026-06-08"])  # 6/8 = \u672c\u5468 partial
        out = _drop_incomplete_tail_bar(df, "1w", now_utc=_now("2026-06-09 00:10"))
        assert len(out) == 2
        assert out.index[-1].date().isoformat() == "2026-06-01"

    def test_keeps_last_week_complete_bar(self):
        """\u4e0a\u5468 open \u7684 bar (\u5df2\u95ed\u5408) - \u4e0d\u52a8."""
        df = _mk_df(["2026-05-25", "2026-06-01"])  # 6/1 = \u4e0a\u5468\u5b8c\u6574
        out = _drop_incomplete_tail_bar(df, "1w", now_utc=_now("2026-06-09 00:10"))
        assert len(out) == 2


class TestUnknownInterval:
    def test_unknown_interval_no_op(self):
        """\u672a\u77e5 interval (\u5982 '4h') - \u4fdd\u5b88\u4e0d drop, \u4ec5 logger.warning."""
        df = _mk_df(["2026-06-08", "2026-06-09"])
        out = _drop_incomplete_tail_bar(df, "4h", now_utc=_now("2026-06-09 00:10"))
        assert len(out) == 2  # \u4e0d drop
