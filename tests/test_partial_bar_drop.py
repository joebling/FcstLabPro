"""Lesson 0609: partial bar drop \u2014 \u9632\u6b62\u63a8\u7406\u8bfb\u53d6 UTC \u5f53\u65e5\u672a\u95ed\u5408\u7684 K \u7ebf.

\u80cc\u666f: 2026-06-07/08/09 \u751f\u4ea7\u4e8b\u6545 \u2014 cron \u5728 UTC 00:10 \u62c9\u6570\u636e,
Binance API \u8fd4\u56de\u7684\u5f53\u65e5 partial bar (\u624d\u5f00 10 \u5206\u949f) \u88ab\u5f53\u4f5c\u201c\u4eca\u65e5 close\u201d,
\u5bfc\u81f4 regime \u8bef\u5224 + entry/exit \u4ef7\u9519\u4f4d. \u8be6\u89c1 docs/lessons/lesson_0609_partial_bar.md.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from scripts.live_signal import drop_partial_bar


def _mk_df(dates: list[str]) -> pd.DataFrame:
    idx = pd.to_datetime(dates)
    return pd.DataFrame({"close": list(range(len(dates)))}, index=idx)


def _now(date_str: str) -> datetime:
    """\u8f85\u52a9: \u6784\u9020\u4e00\u4e2a UTC datetime \u4ee3\u8868'\u4eca\u5929'."""
    return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)


class TestDropPartialBar:
    """\u672b\u5c3e\u662f\u5f53\u65e5 partial bar \u2192 drop; \u672b\u5c3e\u662f\u6628\u65e5\u53ca\u4e4b\u524d \u2192 \u4fdd\u7559."""

    def test_drops_when_last_bar_is_today_utc(self):
        df = _mk_df(["2026-06-07", "2026-06-08", "2026-06-09"])
        out = drop_partial_bar(df, now_utc=_now("2026-06-09 00:10"))
        assert len(out) == 2
        assert out.index[-1].date().isoformat() == "2026-06-08"

    def test_keeps_when_last_bar_is_yesterday(self):
        df = _mk_df(["2026-06-07", "2026-06-08"])
        out = drop_partial_bar(df, now_utc=_now("2026-06-09 00:10"))
        assert len(out) == 2  # \u4e0d\u52a8
        assert out.index[-1].date().isoformat() == "2026-06-08"

    def test_drops_future_bar_defensively(self):
        """\u672b\u5c3e\u662f\u672a\u6765\u65e5\u671f (\u65f6\u949f\u504f\u5dee/\u4e0a\u6e38\u9519\u4f4d) \u2014 \u540c\u6837\u4e22\u5f03."""
        df = _mk_df(["2026-06-07", "2026-06-08", "2026-06-10"])
        out = drop_partial_bar(df, now_utc=_now("2026-06-09 00:10"))
        assert out.index[-1].date().isoformat() == "2026-06-08"

    def test_raises_when_only_partial_bar(self):
        """\u4ec5\u6709\u5f53\u65e5 partial bar (\u6570\u636e\u7a97\u53e3\u592a\u77ed) \u2014 \u62d2\u7edd\u51fa\u4fe1\u53f7."""
        df = _mk_df(["2026-06-09"])
        with pytest.raises(ValueError, match="\u6570\u636e\u7a97\u53e3\u592a\u77ed"):
            drop_partial_bar(df, now_utc=_now("2026-06-09 00:10"))

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame({"close": []}, index=pd.DatetimeIndex([], name="date"))
        out = drop_partial_bar(df, now_utc=_now("2026-06-09 00:10"))
        assert out.empty

    def test_now_utc_default_uses_real_clock(self):
        """\u751f\u4ea7\u8c03\u7528\u4e0d\u4f20 now_utc \u65f6, \u5e94\u4f7f\u7528\u5b9e\u9645\u65f6\u949f \u2014 \u4ec5\u9a8c\u8bc1\u4e0d\u62a5\u9519."""
        df = _mk_df(["2020-01-01", "2020-01-02"])  # \u8db3\u591f\u8001\u7684\u6570\u636e
        out = drop_partial_bar(df)
        assert len(out) == 2  # \u90fd\u662f\u8fc7\u53bb, \u4e0d drop


class TestReplaysLesson0609Bug:
    """\u56de\u653e\u751f\u4ea7\u4e8b\u6545: 6/7 UTC 00:10 \u62c9\u6570\u636e \u2192 \u672b\u5c3e\u662f 6/7 partial bar."""

    def test_replays_2026_06_07_incident(self):
        """\u4e8b\u6545\u5f53\u5929: csv \u672b\u5c3e\u662f 2026-06-07 partial bar (close=60865.64),
        \u4fee\u590d\u540e\u5e94\u8be5\u4e22\u5f03, \u7559\u4e0b 6/6 \u4f5c\u4e3a\u6700\u65b0\u5b8c\u6574 bar.\n        """
        df = pd.DataFrame(
            {"close": [73617.51, 71408.90, 66760.83, 64142.75, 61056.47, 60884.62, 60865.64]},
            index=pd.to_datetime([
                "2026-05-28", "2026-06-01", "2026-06-02",
                "2026-06-03", "2026-06-05", "2026-06-06",
                "2026-06-07",  # \u2190 partial bar (\u4e8b\u6545\u73b0\u573a, close \u662f\u65e9\u76d8\u77ac\u65f6\u4ef7)
            ]),
        )
        out = drop_partial_bar(df, now_utc=_now("2026-06-07 00:10"))
        assert out.index[-1].date().isoformat() == "2026-06-06"
        # \u4fee\u590d\u540e\u7528 6/6 close \u7b97 regime: \u4e0d\u4f1a\u8bef\u89e6\u53d1\u718a\u5e02
        assert out["close"].iloc[-1] == 60884.62
