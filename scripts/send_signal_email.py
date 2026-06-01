#!/usr/bin/env python3
"""发送每日交易信号邮件 — v0305 模型无关版.

通过 SMTP 将信号 JSON 以格式化邮件发送到指定邮箱。
支持任意 production 模型 (E1, E8, ...)，从 JSON 中读取模型元信息。

环境变量:
    SMTP_HOST     SMTP 服务器地址 (默认 smtp.qq.com)
    SMTP_PORT     SMTP 端口 (默认 465, SSL)
    SMTP_USER     发件人邮箱
    SMTP_PASS     授权码（非登录密码）
    MAIL_TO       收件人邮箱，多个用逗号分隔

Usage:
    python scripts/send_signal_email.py signals/signal_2026-03-08.json
"""

from __future__ import annotations

import json
import os
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

try:
    from scripts.email_model_semantics import (
        build_model_semantics_html,
        model_semantics_text,
    )
except ImportError:  # 兼容 `python scripts/send_signal_email.py ...`
    from email_model_semantics import (  # type: ignore
        build_model_semantics_html,
        model_semantics_text,
    )

load_dotenv()

# =====================================================================
# Signal Style Mapping
# =====================================================================

SIGNAL_STYLE: dict[str, dict[str, str]] = {
    "BUY":    {"emoji": "🟢", "color": "#22c55e", "label": "买入"},
    "HOLD":   {"emoji": "🟡", "color": "#f59e0b", "label": "持有中"},
    "SELL":   {"emoji": "🔴", "color": "#ef4444", "label": "卖出"},
    "SILENT": {"emoji": "⚪", "color": "#6b7280", "label": "静默"},
}


# =====================================================================
# HTML Builders (private helpers)
# =====================================================================

def _build_signal_card(data: dict) -> str:
    """信号卡片: 信号类型 + 原因."""
    signal = data.get("signal", "SILENT")
    style = SIGNAL_STYLE.get(signal, SIGNAL_STYLE["SILENT"])
    reason = data.get("reason", "")
    color = style["color"]

    return f"""
    <div style="background: {color}15; border-left: 4px solid {color};
                border-radius: 0 8px 8px 0; padding: 16px; margin-bottom: 16px;">
        <span style="font-size: 22px; font-weight: 600; color: {color};">
            {style['emoji']} {style['label']}
        </span><br>
        <span style="color: #374151; font-size: 14px;">{reason}</span>
    </div>
    """


def _build_regime_card(data: dict) -> str:
    """市场状态卡片: Regime 指示器."""
    regime = data.get("regime", "未知")
    detail = data.get("regime_detail", "")
    is_bear = "熊市" in regime and "非" not in regime
    dot = "🔴" if is_bear else "🟢"

    return f"""
    <div style="background: #f3f4f6; border-radius: 8px; padding: 12px 16px;
                margin-bottom: 16px;">
        <span style="color: #6b7280; font-size: 13px;">市场状态</span><br>
        <span style="font-size: 16px; font-weight: 600; color: #111827;">
            {dot} {regime}
        </span>
        {f'<br><span style="color: #6b7280; font-size: 12px;">{detail}</span>' if detail else ''}
    </div>
    """


def _build_position_card(data: dict) -> str:
    """持仓状态卡片: 仅持仓中显示."""
    pos = data.get("position", {})
    if not pos.get("in_position"):
        return ""

    entry_price = pos.get("entry_price", 0)
    entry_date = pos.get("entry_date", "")
    days_held = pos.get("days_held", 0)
    floating_pnl = pos.get("floating_pnl", 0)
    T = data.get("strategy", {}).get("T", 21)

    pnl_color = "#22c55e" if floating_pnl >= 0 else "#ef4444"
    progress_pct = min(int(days_held / T * 100), 100) if T > 0 else 0

    return f"""
    <div style="background: #fffbeb; border: 1px solid #fbbf24; border-radius: 8px;
                padding: 16px; margin-bottom: 16px;">
        <p style="color: #92400e; font-size: 13px; font-weight: 600;
                  margin: 0 0 8px 0;">📊 持仓状态</p>
        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
            <tr>
                <td style="color: #6b7280; padding: 2px 0;">买入价</td>
                <td style="text-align: right; font-weight: 600;">${entry_price:,.2f}</td>
            </tr>
            <tr>
                <td style="color: #6b7280; padding: 2px 0;">买入日</td>
                <td style="text-align: right;">{entry_date}</td>
            </tr>
            <tr>
                <td style="color: #6b7280; padding: 2px 0;">浮盈</td>
                <td style="text-align: right; font-weight: 600; color: {pnl_color};">
                    {floating_pnl:+.2%}
                </td>
            </tr>
            <tr>
                <td style="color: #6b7280; padding: 2px 0;">持仓天数</td>
                <td style="text-align: right;">第{days_held}天/{T}天</td>
            </tr>
        </table>
        <div style="background: #e5e7eb; border-radius: 4px; height: 8px;
                    overflow: hidden; margin-top: 8px;">
            <div style="background: #f59e0b; height: 100%; width: {progress_pct}%;
                        border-radius: 4px;"></div>
        </div>
    </div>
    """


def _build_history_card(data: dict) -> str:
    """历史战绩卡片."""
    hist = data.get("history", {})
    total = hist.get("total_trades", 0)

    if total == 0:
        return """
        <div style="background: #f3f4f6; border-radius: 8px; padding: 12px 16px;
                    margin-bottom: 16px;">
            <span style="color: #6b7280; font-size: 13px;">📈 历史战绩</span><br>
            <span style="color: #9ca3af; font-size: 14px;">尚无历史交易</span>
        </div>
        """

    wins = hist.get("wins", 0)
    win_rate = hist.get("win_rate", 0)
    avg_pnl = hist.get("avg_pnl", 0)
    recent = hist.get("recent", [])

    avg_color = "#22c55e" if avg_pnl >= 0 else "#ef4444"

    # 最近交易明细
    recent_rows = ""
    for t in recent[:3]:  # 最多显示 3 笔
        pnl_str = t.get("pnl", "")
        is_win = not pnl_str.startswith("-")
        icon = "✅" if is_win else "❌"
        recent_rows += f"""
        <tr style="font-size: 13px;">
            <td style="padding: 3px 0; color: #374151;">{t.get('entry','')}→{t.get('exit','')}</td>
            <td style="text-align: center; color: {'#22c55e' if is_win else '#ef4444'};">{pnl_str}</td>
            <td style="text-align: right; color: #6b7280;">{t.get('reason','')} {icon}</td>
        </tr>
        """

    return f"""
    <div style="background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px;
                padding: 16px; margin-bottom: 16px;">
        <p style="color: #166534; font-size: 13px; font-weight: 600;
                  margin: 0 0 8px 0;">📈 历史战绩</p>
        <table style="width: 100%; border-collapse: collapse; font-size: 14px;
                      margin-bottom: 8px;">
            <tr>
                <td style="color: #6b7280;">已完成</td>
                <td style="text-align: center; font-weight: 600;">{total} 笔</td>
                <td style="color: #6b7280; text-align: right;">胜率</td>
                <td style="text-align: right; font-weight: 600;">{win_rate:.0%}</td>
            </tr>
            <tr>
                <td style="color: #6b7280;">均盈</td>
                <td style="text-align: center; font-weight: 600; color: {avg_color};">
                    {avg_pnl:+.2%}
                </td>
                <td colspan="2"></td>
            </tr>
        </table>
        {'<table style="width: 100%; border-collapse: collapse; border-top: 1px solid #d1d5db; padding-top: 6px;">' + recent_rows + '</table>' if recent_rows else ''}
    </div>
    """


def _build_llm_section(llm_analysis: str | None) -> str:
    """AI 策略解读区块."""
    if not llm_analysis:
        return ""

    paragraphs = []
    for line in llm_analysis.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        paragraphs.append(
            f'<p style="margin: 4px 0; font-size: 13px; color: #374151; '
            f'line-height: 1.6;">{line}</p>'
        )

    return f"""
    <div style="background: #f0f4ff; border-left: 4px solid #6366f1;
                border-radius: 0 8px 8px 0; padding: 16px; margin-bottom: 16px;">
        <p style="color: #4f46e5; font-size: 14px; font-weight: 600;
                  margin: 0 0 8px 0;">🤖 AI 策略解读</p>
        {''.join(paragraphs)}
    </div>
    """


def _build_model_info(data: dict) -> str:
    """模型信息区块 (紧凑版)."""
    m = data.get("model", {})
    bt = m.get("backtest", {})
    s = data.get("strategy", {})

    return f"""
    <div style="background: #f3f4f6; border-radius: 8px; padding: 12px 16px;
                margin-bottom: 16px; font-size: 12px; color: #6b7280;
                line-height: 1.6;">
        <b style="color: #374151;">{m.get('name', 'N/A')}</b>
        · {m.get('type', 'N/A')} · {m.get('features', 'N/A')}特征
        · {m.get('label', 'N/A')}<br>
        Kappa={m.get('kappa', 'N/A')}
        · CAGR={bt.get('cagr', 'N/A')}
        · MaxDD={bt.get('max_dd', 'N/A')}
        · PF={bt.get('pf', 'N/A')}
        · Sharpe={bt.get('sharpe', 'N/A')}<br>
        T={s.get('T', 'N/A')}天
        · X={s.get('X', 'N/A')}
        · 变体: {m.get('variant', 'N/A')}
    </div>
    """


def _build_disclaimer(data: dict) -> str:
    """免责声明."""
    kappa = data.get("model", {}).get("kappa", "N/A")
    return f"""
    <div style="border-top: 1px solid #e5e7eb; padding-top: 12px; margin-top: 12px;">
        <p style="color: #9ca3af; font-size: 11px; margin: 0; line-height: 1.5;">
            ⚠️ 本信号由 FcstLabPro 自动生成 (Kappa={kappa})，
            仅基于历史技术面特征的统计模型，不构成投资建议。
            请结合基本面、宏观环境、个人风险承受能力综合判断。
        </p>
    </div>
    """


# =====================================================================
# Public API
# =====================================================================

def build_html(data: dict) -> str:
    """将信号 JSON 转为 HTML 邮件正文."""
    price = data.get("price", 0)
    date = data.get("date", "")
    model_name = data.get("model", {}).get("name", "FcstLabPro")
    variant = data.get("model", {}).get("variant", "")
    strategy_t = data.get("strategy", {}).get("T", 21)

    return f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                 max-width: 600px; margin: 0 auto; padding: 20px; background: #f9fafb;">
        <div style="background: white; border-radius: 12px; padding: 24px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);">

            <!-- 标题 -->
            <h2 style="margin: 0 0 4px 0; color: #111827;">
                🔮 FcstLabPro 每日信号
            </h2>
            <p style="margin: 0 0 20px 0; color: #6b7280; font-size: 14px;">
                {date} · BTC/USDT · {model_name} · T={strategy_t} {variant}
            </p>

            <!-- 价格 -->
            <div style="background: #f3f4f6; border-radius: 8px; padding: 16px;
                        margin-bottom: 16px;">
                <span style="color: #6b7280; font-size: 13px;">当前价格</span><br>
                <span style="font-size: 28px; font-weight: 700; color: #111827;">
                    ${price:,.2f}
                </span>
            </div>

            <!-- 信号 -->
            {_build_signal_card(data)}

            <!-- 市场状态 -->
            {_build_regime_card(data)}

            {_build_position_card(data)}

            <!-- 历史战绩 -->
            {_build_history_card(data)}

            {_build_llm_section(data.get('llm_analysis'))}

            <!-- 风控提醒 -->
            {_build_risk_notes(data)}

            <!-- 模型信息 -->
            {_build_model_info(data)}

            <!-- 模型语义 -->
            {build_model_semantics_html(data)}

            <!-- 免责声明 -->
            {_build_disclaimer(data)}
        </div>
    </body>
    </html>
    """


def _build_risk_notes(data: dict) -> str:
    """风控提醒区块."""
    notes = data.get("risk_notes", [])
    if not notes:
        return ""
    items = "".join(
        f'<p style="margin: 4px 0; font-size: 13px; color: #374151;">{n}</p>'
        for n in notes
    )
    return f"""
    <div style="margin-bottom: 16px;">
        <p style="color: #6b7280; font-size: 13px; margin: 0 0 8px 0;">⚠️ 风控提醒</p>
        {items}
    </div>
    """


def build_plain_text(data: dict) -> str:
    """将信号 JSON 转为纯文本备用正文."""
    signal = data.get("signal", "SILENT")
    style = SIGNAL_STYLE.get(signal, SIGNAL_STYLE["SILENT"])
    m = data.get("model", {})
    bt = m.get("backtest", {})
    s = data.get("strategy", {})
    pos = data.get("position", {})
    hist = data.get("history", {})

    lines = [
        f"FcstLabPro 每日信号 — {m.get('name', 'N/A')}",
        "═" * 40,
        f"日期: {data.get('date', '')}",
        f"价格: ${data.get('price', 0):,.2f}",
        f"信号: {style['emoji']} {style['label']}",
        f"原因: {data.get('reason', '')}",
        f"Regime: {data.get('regime', '')} {data.get('regime_detail', '')}",
        "",
    ]

    if pos.get("in_position"):
        lines += [
            f"持仓: 买入于 {pos.get('entry_date')} @ ${pos.get('entry_price', 0):,.2f}",
            f"      浮盈 {pos.get('floating_pnl', 0):+.2%}, 第{pos.get('days_held', 0)}天",
            "",
        ]

    total_trades = hist.get("total_trades", 0)
    if total_trades > 0:
        lines.append(
            f"战绩: {total_trades} 笔 | "
            f"胜率 {hist.get('win_rate', 0):.0%} | "
            f"均盈 {hist.get('avg_pnl', 0):+.2%}"
        )
    else:
        lines.append("战绩: 尚无历史交易")

    lines += [
        "",
        f"模型: {m.get('name', 'N/A')} {m.get('version', '')}",
        f"  {m.get('type', 'N/A')} | {m.get('features', 'N/A')}特征 | Kappa={m.get('kappa', 'N/A')}",
        f"  CAGR={bt.get('cagr', 'N/A')} | MaxDD={bt.get('max_dd', 'N/A')} | PF={bt.get('pf', 'N/A')}",
    ]
    lines += model_semantics_text(data)
    lines += [
        "═" * 40,
        "⚠️ 不构成投资建议",
    ]

    return "\n".join(lines)


# =====================================================================
# Email Sending
# =====================================================================

def send_email(signal_path: str) -> bool:
    """发送信号邮件."""
    smtp_host = os.environ.get("SMTP_HOST", "smtp.qq.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    mail_to = os.environ.get("MAIL_TO", "")

    if not smtp_user or not smtp_pass:
        print("⚠️ 未配置 SMTP_USER / SMTP_PASS，跳过邮件发送")
        return False

    if not mail_to:
        print("⚠️ 未配置 MAIL_TO，跳过邮件发送")
        return False

    with open(signal_path) as f:
        data = json.load(f)

    # 提取邮件元信息
    date = data.get("date", "")
    signal = data.get("signal", "SILENT")
    style = SIGNAL_STYLE.get(signal, SIGNAL_STYLE["SILENT"])
    price = data.get("price", 0)
    model_name = data.get("model", {}).get("name", "FcstLabPro")
    model_ver = data.get("model", {}).get("version", "")

    # 构建邮件
    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"[BTC] {date[5:] if len(date) > 5 else date} "
        f"{style['emoji']} {style['label']} | "
        f"${price:,.0f} | {model_name} {model_ver}"
    )
    msg["From"] = smtp_user
    msg["To"] = mail_to

    # 纯文本备用
    msg.attach(MIMEText(build_plain_text(data), "plain", "utf-8"))

    # HTML 正文
    msg.attach(MIMEText(build_html(data), "html", "utf-8"))

    # 附件: 原始 JSON
    attachment = MIMEText(
        json.dumps(data, indent=2, ensure_ascii=False), "plain", "utf-8"
    )
    attachment.add_header(
        "Content-Disposition", "attachment", filename=f"signal_{date}.json"
    )
    msg.attach(attachment)

    # 发送
    try:
        recipients = [addr.strip() for addr in mail_to.split(",")]
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipients, msg.as_string())
        print(f"✅ 邮件已发送至 {mail_to}")
        return True
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/send_signal_email.py <signal_json_path>")
        sys.exit(1)
    send_email(sys.argv[1])
