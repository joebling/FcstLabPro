"""partial_bar_pnl_replay.py - lesson_0609 trade PnL reassessor.

Purpose
-------
Take a VPS-dumped live state JSON and reassess every closed trade's
entry/exit price against the *true* daily close, producing a Markdown
report of how much partial-bar bug cost (or saved).

Usage
-----
    # 1. On VPS, dump the snapshot first:
    bash deploy/vps/dump_live_snapshot.sh --commit

    # 2. After local pull:
    git pull origin main
    python scripts/research/partial_bar_pnl_replay.py \\
        --state-file data/snapshots/state_e20c-conservative-prune_20260609.json \\
        --ohlcv-file data/snapshots/btc_live_20260609.csv \\
        --output docs/research/lesson_0609_pnl_replay_<date>.md

Design
------
- Read-only: never modifies state or ohlcv files.
- Offline: no network calls, no Binance API.
- Output: pure Markdown to stdout or --output.

Semantic caveat
---------------
The "true close" view answers: "what if entry/exit had executed at the
real daily close instead of partial bar close?" It does NOT model the
counterfactual "what would the model have decided without the bug" -
that requires re-running 137-feature inference (out of scope here).
So pnl_delta is the *price-error* contribution only; the regime-
misjudgement contribution (e.g. 6/7 false bear) is reported separately
as a flag, not as a number.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class TradeRow:
    entry_date: str
    exit_date: str
    entry_price_recorded: float
    entry_price_true: float
    exit_price_recorded: float
    exit_price_true: float
    pnl_recorded: float
    pnl_true: float
    pnl_delta: float
    reason: str
    notes: list[str]

    @property
    def entry_dev_pct(self) -> float:
        if self.entry_price_true == 0:
            return float("nan")
        return self.entry_price_recorded / self.entry_price_true - 1

    @property
    def exit_dev_pct(self) -> float:
        if self.exit_price_true == 0:
            return float("nan")
        return self.exit_price_recorded / self.exit_price_true - 1


def load_state(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def load_ohlcv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    # 'date' may be index or column; normalize to a date-indexed frame
    if "date" not in df.columns:
        df = pd.read_csv(path, index_col=0)
        df.index.name = "date"
    else:
        df = df.set_index("date")
    df.index = pd.to_datetime(df.index).normalize()
    required = {"close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"ohlcv csv missing columns: {missing}")
    return df


def true_close(ohlcv: pd.DataFrame, date_str: str) -> float | None:
    ts = pd.Timestamp(date_str).normalize()
    if ts not in ohlcv.index:
        return None
    return float(ohlcv.at[ts, "close"])


def replay_trade(trade: dict[str, Any], ohlcv: pd.DataFrame) -> TradeRow | None:
    """Return None if trade is not closed yet, or ohlcv missing."""
    if not all(k in trade for k in ("entry_date", "exit_date", "entry_price", "exit_price", "pnl")):
        return None
    ep_true = true_close(ohlcv, trade["entry_date"])
    xp_true = true_close(ohlcv, trade["exit_date"])
    notes: list[str] = []
    if ep_true is None:
        notes.append(f"entry_date {trade['entry_date']} not in ohlcv")
    if xp_true is None:
        notes.append(f"exit_date {trade['exit_date']} not in ohlcv")
    if ep_true is None or xp_true is None:
        return TradeRow(
            entry_date=trade["entry_date"], exit_date=trade["exit_date"],
            entry_price_recorded=trade["entry_price"],
            entry_price_true=float("nan"),
            exit_price_recorded=trade["exit_price"],
            exit_price_true=float("nan"),
            pnl_recorded=trade["pnl"], pnl_true=float("nan"),
            pnl_delta=float("nan"),
            reason=trade.get("reason", ""), notes=notes,
        )
    pnl_true = (xp_true - ep_true) / ep_true
    return TradeRow(
        entry_date=trade["entry_date"], exit_date=trade["exit_date"],
        entry_price_recorded=trade["entry_price"], entry_price_true=ep_true,
        exit_price_recorded=trade["exit_price"], exit_price_true=xp_true,
        pnl_recorded=trade["pnl"], pnl_true=pnl_true,
        pnl_delta=pnl_true - trade["pnl"],
        reason=trade.get("reason", ""), notes=notes,
    )


def format_pct(x: float) -> str:
    if pd.isna(x):
        return "N/A"
    return f"{x:+.2%}"


def format_price(x: float) -> str:
    if pd.isna(x):
        return "N/A"
    return f"{x:,.2f}"


def _is_likely_partial_bar(ohlcv: pd.DataFrame, date_str: str) -> bool:
    """Heuristic: csv 中该日的 volume 远小于最近 7 天中位数 → 可能是 partial bar.

    不是绝对准确 (低成交量日也可能触发), 但可以提醒用户 6/9 类似场景。
    """
    ts = pd.Timestamp(date_str).normalize()
    if ts not in ohlcv.index or "volume" not in ohlcv.columns:
        return False
    vol = float(ohlcv.at[ts, "volume"])
    # 取最近 7 个完整 bar (包含本日) 的中位数
    pos = ohlcv.index.get_loc(ts)
    if pos < 1:
        return False
    recent_vols = ohlcv.iloc[max(0, pos - 6):pos]["volume"].astype(float)
    if recent_vols.empty:
        return False
    median_vol = recent_vols.median()
    return median_vol > 0 and vol < 0.1 * median_vol  # 低于中位数 10%


def render_markdown(model: str, rows: list[TradeRow], state: dict[str, Any],
                    ohlcv: pd.DataFrame) -> str:
    lines: list[str] = []
    lines.append(f"# Partial Bar PnL Replay - `{model}`")
    lines.append("")
    # State JSON 没有 updated_at 字段 — 回退到 last_signal_date (阶段性代理)
    updated = state.get("updated_at") or state.get("last_signal_date", "unknown")
    lines.append(f"State last signal: `{updated}`")
    lines.append(f"In-position: `{state.get('in_position', '?')}`")
    lines.append(f"Closed trades reassessed: **{len(rows)}**")
    lines.append("")

    # Partial bar warnings: 检查 trade 在 csv 末尾是否是 partial
    partial_warnings: list[str] = []
    for r in rows:
        if _is_likely_partial_bar(ohlcv, r.entry_date):
            partial_warnings.append(
                f" entry_date {r.entry_date} 看起来是 csv 中的 partial bar "
                f"(volume 远低于近 7 天中位数). entry_true 不准, 等 UTC 下一日重跑。"
            )
        if _is_likely_partial_bar(ohlcv, r.exit_date):
            partial_warnings.append(
                f" exit_date {r.exit_date} 看起来是 csv 中的 partial bar. "
                f"exit_true / pnl_delta 不准, 等 UTC 下一日重跑。"
            )
    if partial_warnings:
        lines.append("##  Partial Bar Warnings")
        lines.append("")
        for w in partial_warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("## Per-trade reassessment")
    lines.append("")
    lines.append("| Entry | Exit | Entry rec | Entry true | Entry dev | "
                 "Exit rec | Exit true | Exit dev | PnL rec | PnL true | PnL delta | Reason |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in rows:
        lines.append(
            f"| {r.entry_date} | {r.exit_date} "
            f"| {format_price(r.entry_price_recorded)} | {format_price(r.entry_price_true)} "
            f"| **{format_pct(r.entry_dev_pct)}** "
            f"| {format_price(r.exit_price_recorded)} | {format_price(r.exit_price_true)} "
            f"| **{format_pct(r.exit_dev_pct)}** "
            f"| {format_pct(r.pnl_recorded)} | {format_pct(r.pnl_true)} "
            f"| **{format_pct(r.pnl_delta)}** "
            f"| {r.reason} |"
        )
    lines.append("")

    # Aggregate
    valid = [r for r in rows if not pd.isna(r.pnl_delta)]
    if valid:
        total_delta = sum(r.pnl_delta for r in valid)
        # pnl_delta = pnl_true - pnl_recorded
        #   > 0  -> true better than recorded -> bug HURT the account
        #   < 0  -> true worse than recorded  -> bug HELPED the account
        n_hurt = sum(1 for r in valid if r.pnl_delta > 0)
        n_helped = sum(1 for r in valid if r.pnl_delta < 0)
        n_neutral = sum(1 for r in valid if r.pnl_delta == 0)
        lines.append("## Aggregate")
        lines.append("")
        lines.append(f"- Trades with valid reassessment: **{len(valid)}**")
        lines.append(f"- Net cumulative PnL delta (true - recorded): "
                     f"**{format_pct(total_delta)}**  "
                     f"({'bug HURT account' if total_delta > 0 else 'bug HELPED account' if total_delta < 0 else 'no net impact'})")
        if n_hurt > 0:
            worst_hurt = max(valid, key=lambda r: r.pnl_delta)
            lines.append(f"- Bug HURT the account: **{n_hurt}** trades "
                         f"(worst {format_pct(worst_hurt.pnl_delta)} on {worst_hurt.exit_date})")
        else:
            lines.append("- Bug HURT the account: **0** trades")
        if n_helped > 0:
            best_help = min(valid, key=lambda r: r.pnl_delta)
            lines.append(f"- Bug HELPED the account: **{n_helped}** trades "
                         f"(best {format_pct(best_help.pnl_delta)} on {best_help.exit_date})")
        else:
            lines.append("- Bug HELPED the account: **0** trades")
        lines.append(f"- Neutral: {n_neutral}")
        lines.append("")

    # Caveats footer
    lines.append("## Caveats")
    lines.append("")
    lines.append("- 'PnL delta' captures **price-error only** (entry/exit at "
                 "partial close vs true close). It does NOT capture the "
                 "**regime-misjudgement** contribution (e.g. a 6/7 false bear "
                 "exit that should not have happened at all) - that requires "
                 "full re-simulation including model inference.")
    lines.append("- 'Reason' tagged `bear_market` on a day whose true 63d return "
                 "was actually above -10% is a regime misjudgement - flag for "
                 "qualitative review.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Generated by scripts/research/partial_bar_pnl_replay.py "
                 "(lesson_0609 followup, V1)*")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--state-file", type=Path, required=True,
                   help="Path to state JSON (e.g. data/snapshots/state_<model>_<date>.json)")
    p.add_argument("--ohlcv-file", type=Path, required=True,
                   help="Path to OHLCV csv with 'date' index/column and 'close' column")
    p.add_argument("--output", type=Path, default=None,
                   help="Optional output path; default stdout")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    state = load_state(args.state_file)
    ohlcv = load_ohlcv(args.ohlcv_file)

    model = args.state_file.stem.replace("state_", "").rsplit("_", 1)[0]
    history = state.get("history", [])
    rows = [r for r in (replay_trade(t, ohlcv) for t in history) if r is not None]

    md = render_markdown(model, rows, state, ohlcv)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md)
        print(f"Report written to {args.output} ({len(rows)} trades reassessed)",
              file=sys.stderr)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
