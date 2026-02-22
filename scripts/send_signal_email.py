#!/usr/bin/env python3
"""发送每日交易信号邮件.

通过 SMTP 将信号 JSON 以格式化邮件发送到指定邮箱。
支持 QQ 邮箱、Gmail 等 SMTP 服务。

环境变量:
    SMTP_HOST     SMTP 服务器地址 (默认 smtp.qq.com)
    SMTP_PORT     SMTP 端口 (默认 465, SSL)
    SMTP_USER     发件人邮箱
    SMTP_PASS     授权码（非登录密码）
    MAIL_TO       收件人邮箱，多个用逗号分隔

Usage:
    python scripts/send_signal_email.py signals/signal_2026-02-13.json
"""

import json
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

def _build_llm_section(llm_analysis: str | None) -> str:
    """生成 AI 策略解读的 HTML 区块."""
    if not llm_analysis:
        return ""

    # 将 markdown 格式的分析转换为 HTML 段落
    paragraphs = []
    for line in llm_analysis.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # 加粗处理
        import re
        line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
        paragraphs.append(
            f'<p style="margin: 4px 0; font-size: 13px; color: #374151; line-height: 1.6;">{line}</p>'
        )

    return f"""
            <div style="background: #f0f4ff; border-left: 4px solid #6366f1; border-radius: 0 8px 8px 0; padding: 16px; margin-bottom: 16px;">
                <p style="color: #4f46e5; font-size: 14px; font-weight: 600; margin: 0 0 8px 0;">🤖 AI 策略解读 (Gemini)</p>
                {"".join(paragraphs)}
            </div>
    """


def build_html(data: dict) -> str:
    """将信号 JSON 转为 HTML 邮件正文（含模型元信息）."""

    bull_prob = data["bull_prob"]
    bear_prob = data["bear_prob"]
    signal = data.get("signal_display", data.get("signal", ""))
    price = data["price"]
    date = data["date"]
    position = data["position_pct"]
    action = data["action"]
    risk_level = data.get("risk_level", "")
    risk_notes = data.get("risk_notes", [])

    # 新增：模型元信息
    model_version = data.get("model_version", {})
    strategy_version = data.get("strategy_version", {})
    kappa = data.get("kappa", {})
    label_strategy = data.get("label_strategy", {})
    feature_set = data.get("feature_set", {})

    # 概率条
    bull_pct = int(bull_prob * 100)
    bear_pct = int(bear_prob * 100)

    # 信号颜色
    signal_code = data.get("signal", "NEUTRAL")
    color_map = {
        "BULL": "#22c55e",
        "BEAR": "#ef4444",
        "NEUTRAL": "#6b7280",
        "VOLATILE": "#f59e0b",
    }
    signal_color = color_map.get(signal_code, "#6b7280")

    # 新增：模型信息区块
    model_info_html = f'''
        <div style="background: #f3f4f6; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; font-size: 13px; color: #374151;">
            <b>模型版本</b>：Bull={model_version.get('bull','N/A')}, Bear={model_version.get('bear','N/A')}<br>
            <b>Kappa</b>：Bull={kappa.get('bull','N/A')}, Bear={kappa.get('bear','N/A')}<br>
            <b>标签策略</b>：Bull={label_strategy.get('bull','N/A')}, Bear={label_strategy.get('bear','N/A')}<br>
            <b>特征集</b>：Bull={', '.join(feature_set.get('bull', []))}，Bear={', '.join(feature_set.get('bear', []))}
        </div>
    '''

    html = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9fafb;">
        <div style="background: white; border-radius: 12px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">

            <!-- 标题 -->
            <h2 style="margin: 0 0 4px 0; color: #111827;">🔮 FcstLabPro 每日信号</h2>
            <p style="margin: 0 0 20px 0; color: #6b7280; font-size: 14px;">
                {date} · BTC/USDT · Bull T=21天 / Bear T=28天
            </p>

            <!-- 模型信息 -->
            {model_info_html}

            <!-- 价格 -->
            <div style="background: #f3f4f6; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                <span style="color: #6b7280; font-size: 13px;">当前价格</span><br>
                <span style="font-size: 28px; font-weight: 700; color: #111827;">${price:,.2f}</span>
            </div>

            <!-- 信号 -->
            <div style="background: {signal_color}15; border-left: 4px solid {signal_color}; border-radius: 0 8px 8px 0; padding: 16px; margin-bottom: 16px;">
                <span style="font-size: 22px; font-weight: 600; color: {signal_color};">{signal}</span><br>
                <span style="color: #374151; font-size: 14px;">{action}</span>
            </div>

            <!-- 概率 -->
            <table style="width: 100%; margin-bottom: 16px; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px 0; color: #374151; font-size: 14px;">🐂 大涨概率</td>
                    <td style="padding: 8px 0; width: 55%;">
                        <div style="background: #e5e7eb; border-radius: 4px; height: 20px; overflow: hidden;">
                            <div style="background: #22c55e; height: 100%; width: {bull_pct}%; border-radius: 4px; text-align: center; color: white; font-size: 12px; line-height: 20px;">{bull_prob:.1%}</div>
                        </div>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #374151; font-size: 14px;">🐻 大跌概率</td>
                    <td style="padding: 8px 0;">
                        <div style="background: #e5e7eb; border-radius: 4px; height: 20px; overflow: hidden;">
                            <div style="background: #ef4444; height: 100%; width: {bear_pct}%; border-radius: 4px; text-align: center; color: white; font-size: 12px; line-height: 20px;">{bear_prob:.1%}</div>
                        </div>
                    </td>
                </tr>
            </table>

            <!-- 仓位 -->
            <div style="background: #f3f4f6; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                <span style="color: #6b7280; font-size: 13px;">建议仓位</span><br>
                <div style="margin-top: 8px;">
                    <div style="background: #e5e7eb; border-radius: 4px; height: 24px; overflow: hidden;">
                        <div style="background: #3b82f6; height: 100%; width: {position}%; border-radius: 4px; text-align: center; color: white; font-size: 13px; line-height: 24px; font-weight: 600;">{position}%</div>
                    </div>
                </div>
            </div>

            <!-- 风控提醒 -->
            <div style="margin-bottom: 16px;">
                <p style="color: #6b7280; font-size: 13px; margin: 0 0 8px 0;">风控提醒</p>
                {"".join(f'<p style="margin: 4px 0; font-size: 13px; color: #374151;">{note}</p>' for note in risk_notes)}
            </div>

            <!-- AI 策略解读 -->
            {_build_llm_section(data.get("llm_analysis"))}

            <!-- 免责 -->
            <div style="border-top: 1px solid #e5e7eb; padding-top: 12px; margin-top: 12px;">
                <p style="color: #9ca3af; font-size: 11px; margin: 0; line-height: 1.5;">
                    ⚠️ 本信号由 FcstLabPro 自动生成，仅基于历史技术面特征的统计模型（Kappa: Bull={kappa.get('bull','N/A')}, Bear={kappa.get('bear','N/A')}），
                    不构成投资建议。请结合基本面、宏观环境、个人风险承受能力综合判断。
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    return html


def send_email(signal_path: str):
    """发送信号邮件."""

    # 读取环境变量
    smtp_host = os.environ.get("SMTP_HOST", "smtp.qq.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    mail_to = os.environ.get("MAIL_TO", "")

    if not smtp_user or not smtp_pass:
        print("⚠️ 未配置 SMTP_USER / SMTP_PASS，跳过邮件发送")
        print("   请设置环境变量：")
        print("   SMTP_USER=your_email@qq.com")
        print("   SMTP_PASS=your_authorization_code")
        return False

    if not mail_to:
        print("⚠️ 未配置 MAIL_TO，跳过邮件发送")
        return False

    # 读取信号
    with open(signal_path) as f:
        data = json.load(f)

    date = data["date"]
    signal_code = data.get("signal", "UNKNOWN")
    signal_display = data.get("signal_display", signal_code)

    # 新增：模型元信息变量，供后续模板使用
    model_version = data.get("model_version", {})
    kappa = data.get("kappa", {})
    label_strategy = data.get("label_strategy", {})
    feature_set = data.get("feature_set", {})

    # 构建邮件
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[BTC信号] {date} {signal_display} — FcstLabPro Bull={model_version.get('bull','N/A')}, Bear={model_version.get('bear','N/A')}"
    msg["From"] = smtp_user
    msg["To"] = mail_to

    # 纯文本备用
    text_body = (
        f"FcstLabPro 每日信号\n"
        f"日期: {date}\n"
        f"价格: ${data['price']:,.2f}\n"
        f"Bull: {data['bull_prob']:.1%}  Bear: {data['bear_prob']:.1%}\n"
        f"信号: {signal_display}\n"
        f"仓位: {data['position_pct']}%\n"
        f"操作: {data['action']}\n"
        f"模型版本: Bull={model_version.get('bull','N/A')}, Bear={model_version.get('bear','N/A')}\n"
        f"Kappa: Bull={kappa.get('bull','N/A')}, Bear={kappa.get('bear','N/A')}\n"
        f"标签策略: Bull={label_strategy.get('bull','N/A')}, Bear={label_strategy.get('bear','N/A')}\n"
        f"特征集: Bull={', '.join(feature_set.get('bull', []))}，Bear={', '.join(feature_set.get('bear', []))}\n"
    )
    msg.attach(MIMEText(text_body, "plain", "utf-8"))

    # HTML 正文
    html_body = build_html(data)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # 附件：原始 JSON
    attachment = MIMEText(json.dumps(data, indent=2, ensure_ascii=False), "plain", "utf-8")
    attachment.add_header("Content-Disposition", "attachment", filename=f"signal_{date}.json")
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
