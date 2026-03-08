"""LLM 策略分析师 — 基于 Gemini API 对模型信号做智能解读.

调用 Google Gemini 2.0 Flash 模型，结合模型输出、近期 K 线、历史战绩，
生成自然语言策略解读，嵌入每日信号邮件。

环境变量:
    GEMINI_API_KEY    Google AI API Key

Usage:
    from src.llm.analyst import generate_analysis
    analysis = generate_analysis(signal_data, klines, {}, history, position)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# ── System Prompt ──

SYSTEM_PROMPT = """你是一位专业的加密货币量化分析师，负责解读 FcstLabPro 预测系统的信号。

## 系统架构

- **单模型架构**: 一个 LightGBM 梯度提升树模型
- **标签定义**: 在 RSI<45 且价格<SMA50 的超卖/弱势环境中，
  寻找未来 T 天内 ≥X% 的反弹机会
- **信号类型**: BUY (开仓), HOLD (继续持仓), SELL (平仓), SILENT (无信号)
- **策略变体**: 止盈 (+X% 即平仓) + regime 开关 (63天收益≤-10% 时静默)

### 特征集 (129 个特征, 已去污染)
- **technical**: SMA/EMA/MACD/BB/ATR/动量 (已移除 RSI/SMA 避免与标签泄漏)
- **volume**: 成交量均线、量比、OBV、VWAP
- **flow**: 资金流向代理指标
- **market_structure**: 模拟资金费率、CVD、量价背离
- **external_fgi**: Fear & Greed Index 及其移动平均

⚠️ 不包含：链上数据、新闻/社交媒体、宏观经济指标、基本面数据

### 你的分析原则
1. 模型 Kappa 较低 (约 0.19-0.75)，永远提醒用户预测力有限
2. 结合近期 K 线走势判断技术面以外的驱动因素
3. 如果提供了历史战绩，分析胜负模式（哪种退出方式胜率高、哪种市场条件下表现好）
4. 如果有当前持仓，重点分析持仓风险和潜在退出时机
5. 不要重复原始数据，直接给出分析判断
"""

USER_PROMPT_TEMPLATE = """以下是今日的预测信号和近期走势数据，请给出分析。

## 今日信号
- 日期: {date}
- BTC 当前价格: ${price:,.2f}
- 信号: {signal_display}
- 原因: {reason}
- Regime: {regime}

## 持仓状态
{position_info}

## 近 7 天 K 线走势
{kline_table}

## 关键技术指标（当前值）
{indicators}

## 历史战绩
{history_info}

请用中文给出以下分析（总计 300 字以内，简洁有力）：

1. **信号解读**：结合技术指标解释为什么给出这个信号
2. **市场结构**：当前趋势、关键支撑位和压力位
3. **风险提示**：模型局限性和需要关注的风险因素
4. **战绩洞察**（如有历史数据）：分析胜负模式、哪种退出方式更有效

注意：不要重复我给你的原始数据，直接给出分析判断。"""


# ── Formatters ──

def _format_kline_table(klines: list[dict]) -> str:
    """将 K 线数据格式化为表格."""
    if not klines:
        return "（无近期数据）"

    lines = ["日期       | 收盘价     | 涨跌幅  | 成交量"]
    lines.append("---------- | ---------- | ------- | ----------")
    for k in klines[-7:]:
        change = k.get("change", 0)
        lines.append(
            f"{k['date']}  | ${k['close']:>9,.2f} | "
            f"{change:>+6.2f}% | {k.get('volume', 0):,.0f}"
        )
    return "\n".join(lines)


def _format_indicators(indicators: dict) -> str:
    """格式化关键技术指标."""
    if not indicators:
        return "（无指标数据）"

    lines = []
    for name, value in indicators.items():
        if isinstance(value, float):
            lines.append(f"- {name}: {value:.4f}")
        else:
            lines.append(f"- {name}: {value}")
    return "\n".join(lines)


# ── Gemini API ──

def _call_gemini(system_prompt: str, user_prompt: str, api_key: str) -> Optional[str]:
    """调用 Gemini API（使用 urllib，无需额外依赖）."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 800,
            "topP": 0.9,
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        candidates = result.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "")

        logger.warning("Gemini 返回结果无内容: %s", json.dumps(result, ensure_ascii=False)[:200])
        return None

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        logger.error("Gemini API HTTP 错误 %d: %s", e.code, body[:300])
        return None
    except Exception as e:
        logger.error("Gemini API 调用失败: %s", e)
        return None


# ── Public API ──

def generate_analysis(
    signal_data: dict,
    recent_klines: Optional[list[dict]] = None,
    indicators: Optional[dict] = None,
    trade_history: Optional[dict] = None,
    position: Optional[dict] = None,
) -> Optional[str]:
    """生成 LLM 策略分析.

    Parameters
    ----------
    signal_data : dict
        信号 JSON 数据
    recent_klines : list[dict], optional
        近期 K 线数据
    indicators : dict, optional
        关键技术指标快照
    trade_history : dict, optional
        历史战绩汇总
    position : dict, optional
        当前持仓状态
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.info("未配置 GEMINI_API_KEY，跳过 LLM 分析")
        return None

    # 持仓信息
    position_info = "当前空仓"
    if position and position.get("in_position"):
        position_info = (
            f"持仓中: 买入于 {position.get('entry_date')} @ "
            f"${position.get('entry_price', 0):,.2f}, "
            f"第{position.get('days_held', 0)}天, "
            f"浮盈 {position.get('floating_pnl', 0):+.2%}"
        )

    # 历史战绩信息
    history_info = "尚无历史交易"
    if trade_history and trade_history.get("total_trades", 0) > 0:
        h = trade_history
        history_info = (
            f"已完成 {h['total_trades']} 笔, "
            f"胜率 {h.get('win_rate', 0):.0%}, "
            f"均盈 {h.get('avg_pnl', 0):+.2%}"
        )
        exit_stats = h.get("exit_stats", {})
        if exit_stats:
            parts = []
            for k, v in exit_stats.items():
                wr = v["wins"] / v["count"] if v["count"] > 0 else 0
                parts.append(f"{k}: {v['count']}笔 胜率{wr:.0%}")
            history_info += "\n退出方式: " + ", ".join(parts)

    # 构建 User Prompt
    user_prompt = USER_PROMPT_TEMPLATE.format(
        date=signal_data.get("date", ""),
        price=signal_data.get("price", 0),
        signal_display=signal_data.get("signal_display", ""),
        reason=signal_data.get("reason", ""),
        regime=signal_data.get("regime", ""),
        position_info=position_info,
        kline_table=_format_kline_table(recent_klines or []),
        indicators=_format_indicators(indicators or {}),
        history_info=history_info,
    )

    logger.info("📝 调用 Gemini 生成策略分析...")
    analysis = _call_gemini(SYSTEM_PROMPT, user_prompt, api_key)

    if analysis:
        logger.info("✅ LLM 分析生成成功 (%d 字)", len(analysis))
    else:
        logger.warning("⚠️ LLM 分析生成失败，将跳过")

    return analysis
