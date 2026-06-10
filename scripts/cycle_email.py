#!/usr/bin/env python3
"""周期研判邮件 — 每日第三封 (与模型择时信号正交).

周期研判回答「现在处于牛熊周期哪个位置」(中长期仓位定位),
模型信号回答「现在该不该动仓」(短线择时)。两个正交维度, 独立邮件。

数据全部取自单一真相源:
  - regime / RR 分位 / 动作  <- src.dashboard.data.cycle.build()  (与 dashboard 周期页一致)
  - ahr999                    <- data/external/onchain/ahr999.csv
  - 历史战绩 (事件研究)        <- cycle_stats.regime_event_study()
  - LLM 点评                  <- src.llm.analyst.generate_cycle_analysis()
SMTP 发送复用 send_signal_email.send_mime (DRY)。

隐性时序依赖 (重要): cycle.build() 读 reserve_risk.csv(cron 00:05) + ahr999.csv(00:08),
本邮件随 daily pipeline(00:10) 发, 故二者必须排在 pipeline 之前。改 cron 顺序会害它读旧值。

Usage:
    python scripts/cycle_email.py            # 组装 + LLM + 发送
    python scripts/cycle_email.py --dry-run  # 只打印, 不发不调 LLM
"""
from __future__ import annotations

import argparse
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env", override=False)

from src.serving.paths import BASELINE_OHLCV_PATH, LIVE_OHLCV_PATH  # noqa: E402
from src.dashboard.data import cycle, cycle_core, cycle_stats       # noqa: E402

TOP_ZONE = 70.0
BOTTOM_ZONE = 30.0

_RED = "\U0001F534"
_GREEN = "\U0001F7E2"
_BLUE = "\U0001F535"
_WHITE = "\u26aa"
REGIME_EMOJI = {"top": _RED, "bottom": _GREEN, "neutral": _BLUE}


def _load_price() -> pd.Series:
    """收盘价序列: live 优先, 缺失回退训练基准 (同 compute_ahr999 理念)."""
    path = LIVE_OHLCV_PATH if LIVE_OHLCV_PATH.exists() else BASELINE_OHLCV_PATH
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    return df["close"].astype(float)


def _ahr999_latest() -> tuple:
    s = cycle_core.load_onchain("ahr999.csv")
    if s is None or s.empty:
        return None, None
    from scripts.compute_ahr999 import classify
    v = round(float(s.iloc[-1]), 4)
    return v, classify(v)


def build_cycle_context() -> dict:
    """组装周期邮件全部数据 (html/text/llm 共用单一入口)."""
    c = cycle.build()
    price = _load_price()
    date = price.index[-1].strftime("%Y-%m-%d") if not price.empty else ""
    cur_price = round(float(price.iloc[-1]), 2) if not price.empty else 0.0
    ahr_val, ahr_zone = _ahr999_latest()

    if not c.get("available"):
        return {"available": False, "date": date, "price": cur_price,
                "ahr999_val": ahr_val, "ahr999_zone": ahr_zone}

    rr = cycle_core.load_onchain("reserve_risk.csv")
    es = cycle_stats.regime_event_study(rr, price, TOP_ZONE, BOTTOM_ZONE)
    regime = c["regime"]
    verdict = c["active_verdict"]
    return {
        "available": True, "date": date, "price": cur_price,
        "rr_pct": c["rr_pct"], "rr_pct_legacy": c.get("rr_pct_legacy"),
        "rr_val": c.get("rr_val"),
        "regime_key": regime["key"], "regime_label": regime["label"],
        "regime_desc": regime["desc"], "regime_color": regime["color"],
        "stance": regime["stance"],
        "verdict_label": verdict["label"], "verdict_action": verdict["action"],
        "ahr999_val": ahr_val, "ahr999_zone": ahr_zone,
        "event_study": es,
    }


def _es_rows(ctx: dict, html: bool) -> str:
    es = ctx.get("event_study", {})
    if not es or not es.get("available"):
        return ('<tr><td colspan="4" style="padding:8px;color:#94a3b8">历史战绩数据不可用</td></tr>'
                if html else "  历史战绩数据不可用")
    rows = []
    for side, label, color in (("top", "顶部区", "#f43f5e"), ("bottom", "底部区", "#10b981")):
        blk = es.get(side, {})
        for h in es.get("horizons", []):
            d = blk.get(f"h{h}", {})
            if not d.get("n"):
                continue
            if html:
                rows.append(
                    f'<tr><td style="padding:6px 8px;color:{color};font-weight:600">{label}</td>'
                    f'<td style="padding:6px 8px">后{h}天</td>'
                    f'<td style="padding:6px 8px;text-align:right">{d["avg"]:+}%</td>'
                    f'<td style="padding:6px 8px;text-align:right">命中{d["hit"]}% ({d["n"]}样本)</td></tr>'
                )
            else:
                rows.append(f"  {label} 后{h}天: 均收益{d['avg']:+}% 命中{d['hit']}% ({d['n']}样本)")
    return "".join(rows) if html else "\n".join(rows)


def build_cycle_html(ctx: dict) -> str:
    if not ctx.get("available"):
        return ('<div style="font-family:sans-serif;padding:20px">'
                f'<h2>周期研判 · {ctx.get("date","")}</h2>'
                '<p style="color:#f43f5e">周期数据未就绪 (reserve_risk / ahr999 缺失或过期)。'
                '请检查 00:05 / 00:08 的 cron 是否在 pipeline 之前跑完。</p></div>')
    color = ctx["regime_color"]
    rr_legacy = ctx.get("rr_pct_legacy")
    legacy_txt = f' · 旧口径 {rr_legacy}%' if rr_legacy is not None else ""
    ahr = f'{ctx["ahr999_val"]} [{ctx["ahr999_zone"]}]' if ctx.get("ahr999_val") is not None else "N/A"
    llm = ctx.get("llm_analysis")
    llm_html = (f'<div style="margin-top:16px;padding:14px;background:#f8fafc;border-radius:8px;'
                f'border-left:4px solid #6366f1"><div style="font-weight:700;margin-bottom:6px">'
                f'AI 周期点评</div><div style="white-space:pre-wrap;line-height:1.6;color:#334155">'
                f'{llm}</div></div>') if llm else ""
    return f"""<div style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto;color:#0f172a">
  <h2 style="margin:0 0 4px">周期研判</h2>
  <div style="color:#64748b;font-size:13px;margin-bottom:16px">{ctx['date']} · BTC ${ctx['price']:,.0f} · 中长期仓位定位 (非短线)</div>

  <div style="padding:18px;border-radius:10px;background:{color}15;border-left:6px solid {color};margin-bottom:16px">
    <div style="font-size:20px;font-weight:800;color:{color}">{ctx['regime_label']}</div>
    <div style="color:#475569;margin:4px 0">{ctx['regime_desc']}</div>
    <div style="font-weight:700;margin-top:8px">动作: {ctx['stance']}</div>
    <div style="color:#64748b;font-size:13px;margin-top:4px">{ctx['verdict_action']}</div>
  </div>

  <table style="width:100%;border-collapse:collapse;margin-bottom:16px;font-size:14px">
    <tr><td style="padding:8px;background:#f1f5f9;border-radius:6px">
      <div style="color:#64748b;font-size:12px">Reserve Risk 分位 (rolling-2y)</div>
      <div style="font-size:22px;font-weight:800;color:{color}">{ctx['rr_pct']}%</div>
      <div style="color:#94a3b8;font-size:12px">0=深底 100=极顶{legacy_txt}</div>
    </td></tr>
    <tr><td style="padding:8px;background:#f1f5f9;border-radius:6px;margin-top:8px">
      <div style="color:#64748b;font-size:12px">ahr999 定投指数</div>
      <div style="font-size:18px;font-weight:700">{ahr}</div>
    </td></tr>
  </table>

  <div style="font-weight:700;margin-bottom:6px">历史战绩 (跨入该区后 BTC 前瞻收益)</div>
  <table style="width:100%;border-collapse:collapse;font-size:13px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">
    {_es_rows(ctx, html=True)}
  </table>
  <div style="color:#94a3b8;font-size:12px;margin-top:4px">命中=方向研判对 (顶部后跌/底部后涨)。事件研究, 非真实成交。</div>

  {llm_html}

  <div style="margin-top:20px;color:#94a3b8;font-size:12px">不构成投资建议。周期研判为单指标中长期定位, 顶部区不等于顶、底部区不等于底。</div>
</div>"""


def build_cycle_text(ctx: dict) -> str:
    if not ctx.get("available"):
        return f"周期研判 · {ctx.get('date','')}\n周期数据未就绪 (reserve_risk/ahr999 缺失或过期)。"
    ahr = f'{ctx["ahr999_val"]} [{ctx["ahr999_zone"]}]' if ctx.get("ahr999_val") is not None else "N/A"
    lines = [
        f"周期研判 · {ctx['date']} · BTC ${ctx['price']:,.0f}",
        "=" * 40,
        f"regime: {ctx['regime_label']} ({ctx['regime_desc']})",
        f"动作: {ctx['stance']}",
        f"  {ctx['verdict_action']}",
        f"Reserve Risk 分位 (rolling-2y): {ctx['rr_pct']}%"
        + (f" | 旧口径 {ctx['rr_pct_legacy']}%" if ctx.get("rr_pct_legacy") is not None else ""),
        f"ahr999: {ahr}",
        "",
        "历史战绩 (跨入该区后 BTC 前瞻收益):",
        _es_rows(ctx, html=False),
    ]
    if ctx.get("llm_analysis"):
        lines += ["", "AI 周期点评:", ctx["llm_analysis"]]
    lines += ["=" * 40, "不构成投资建议。顶部区不等于顶、底部区不等于底。"]
    return "\n".join(lines)


def send_cycle_email(dry_run: bool = False) -> bool:
    ctx = build_cycle_context()

    if not dry_run and ctx.get("available"):
        try:
            from src.llm.analyst import generate_cycle_analysis
            analysis = generate_cycle_analysis(ctx)
            if analysis:
                ctx["llm_analysis"] = analysis
                print(f"周期 LLM 点评已生成 ({len(analysis)} 字)")
        except Exception as e:  # noqa: BLE001
            print(f"周期 LLM 分析失败 (不阻断): {e}")

    emoji = REGIME_EMOJI.get(ctx.get("regime_key"), _WHITE)
    date_short = ctx.get("date", "")[5:] if len(ctx.get("date", "")) > 5 else ctx.get("date", "")
    if ctx.get("available"):
        subject = (f"[周期] {date_short} {emoji} {ctx['regime_label']} | "
                   f"RR {ctx['rr_pct']}% | {ctx['stance']}")
    else:
        subject = f"[周期] {date_short} {_WHITE} 数据未就绪"

    if dry_run:
        print("=== DRY-RUN: 不发送 ===")
        print("Subject:", subject)
        print(build_cycle_text(ctx))
        return True

    from scripts.send_signal_email import send_mime
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg.attach(MIMEText(build_cycle_text(ctx), "plain", "utf-8"))
    msg.attach(MIMEText(build_cycle_html(ctx), "html", "utf-8"))
    return send_mime(msg)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="发送周期研判邮件")
    ap.add_argument("--dry-run", action="store_true", help="只打印, 不发不调 LLM")
    args = ap.parse_args()
    send_cycle_email(dry_run=args.dry_run)
