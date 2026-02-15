"""LLM 策略分析师 — 基于 Gemini API 对模型信号做智能解读.

调用 Google Gemini 2.0 Flash 模型，结合模型输出概率和近期 K 线数据，
生成自然语言策略解读，嵌入每日信号邮件。

环境变量:
    GEMINI_API_KEY    Google AI API Key

Usage:
    from src.llm.analyst import generate_analysis
    analysis = generate_analysis(signal_data, recent_klines)
"""

import json
import logging
import os
from typing import Optional

import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# ── 模型背景 System Prompt ──
SYSTEM_PROMPT = """你是一位专业的加密货币量化分析师，负责解读 FcstLabPro v7 预测系统的信号。

## 你正在使用的预测系统：FcstLabPro v7

### 1. 系统架构
- 双模型架构：Bull 模型和 Bear 模型各自独立预测
  - Bull 模型：Orion-BiX 表格神经网络，预测 P(未来21天内出现 ≥5% 大涨)
  - Bear 模型：LightGBM 梯度提升树，预测 P(未来28天内出现 ≥5% 大跌)
- 两个模型可以同时看多和看空（高波动场景），也可以同时都不触发（震荡场景）

### 2. 标签定义（reversal 策略）
- Bull 前瞻窗口 T=21 天，Bear T=28 天，阈值 X=5%
- 标签看的是未来 T 天内的**极值**（最高/最低价），不是终点价格
- 这意味着：即使标签为"大涨"，21天后的收盘价未必比现在高
- Bull 标签映射：原始标签 2（底部反转=大涨）→ 1，其余 → 0
- Bear 标签映射：原始标签 0（顶部反转=大跌）→ 1，其余 → 0

### 3. 输入特征
- **technical**: SMA/EMA (5/10/20/50/100/200)、均线交叉、RSI (6/14/28)、MACD、布林带、ATR、动量 (1~21日收益率)、波动率
- **volume**: 成交量均线、量比、OBV、VWAP、量价相关性
- **flow**: 资金流向代理指标
- **market_structure**: 模拟资金费率、CVD、买入压力、量价背离
- **external_fgi**: Fear & Greed Index 及其移动平均
- **regime**: 200日均线位置、趋势强度、波动率

⚠️ 不包含：链上数据、新闻/社交媒体、宏观经济指标、基本面数据

### 4. 模型类型
- **Bull**: Orion-BiX 表格神经网络 (基于注意力机制的深度学习模型)
- **Bear**: LightGBM 梯度提升树
- 均为 Walk-Forward 滑动验证

### 5. 实际性能（请重点关注）
- **Bull 模型**: Kappa=0.1122, 年化收益 +26.63%, 卡玛比率 1.53
- **Bear 模型**: Kappa=0.0529, 年化收益待测
- **重要**: Bull 模型 Kappa 虽仅 0.11，但PnL表现优异（年化26.6%），说明高Kappa不等于高收益
- 永远提醒用户：模型预测力有限，不应单独作为交易依据
- Bear 模型 Kappa 较低，且在 BTC 牛市环境下信号稀少，实盘需谨慎

### 6. 交易频率特征
- **中低频交易**: 每周预测一次，信号有效期 21-28 天
- 不适合日内/高频交易
- 建议仓位调整频率：每 1-4 周一次

### 7. 你的分析原则
- 模型概率是**方向性倾向指标**，不是精确概率
- 概率 >60% 说明技术面特征较一致，但仍有大量不确定性
- 结合近期 K 线走势判断技术面以外的驱动因素
- 当 Bull 和 Bear 同时高概率时，说明市场矛盾，应特别谨慎
- 永远提醒用户：模型预测力有限，不应单独作为交易依据
"""

USER_PROMPT_TEMPLATE = """以下是今日的预测信号和近期走势数据，请给出分析。

## 今日信号
- 日期: {date}
- BTC 当前价格: ${price:,.2f}
- 未来21天大涨概率 (Bull): {bull_prob:.1%}
- 未来28天大跌概率 (Bear): {bear_prob:.1%}
- 综合信号: {signal_display}
- 建议仓位: {position_pct}%

## 近 7 天 K 线走势
{kline_table}

## 关键技术指标（当前值）
{indicators}

请用中文给出以下分析（总计 250 字以内，简洁有力）：

1. **信号解读**：结合技术指标解释模型为什么给出这个信号
2. **市场结构**：当前趋势、关键支撑位和压力位
3. **操作建议**：具体的入场区间、止损位、目标位
4. **风险提示**：模型局限性和需要关注的风险因素

注意：不要重复我给你的原始数据，直接给出分析判断。"""


def _format_kline_table(klines: list[dict]) -> str:
    """将 K 线数据格式化为表格."""
    if not klines:
        return "（无近期数据）"

    lines = ["日期       | 收盘价     | 涨跌幅  | 成交量"]
    lines.append("---------- | ---------- | ------- | ----------")
    for k in klines[-7:]:  # 取最近7天
        lines.append(
            f"{k['date']}  | ${k['close']:>9,.2f} | "
            f"{k['change']:>+6.2f}% | {k['volume']:,.0f}"
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


def _call_gemini(system_prompt: str, user_prompt: str, api_key: str) -> Optional[str]:
    """调用 Gemini API（使用 urllib，无需额外依赖）."""

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )

    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 600,
            "topP": 0.9,
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        # 提取文本
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


def generate_analysis(
    signal_data: dict,
    recent_klines: Optional[list[dict]] = None,
    indicators: Optional[dict] = None,
) -> Optional[str]:
    """生成 LLM 策略分析.

    Parameters
    ----------
    signal_data : dict
        信号 JSON 数据，包含 date, price, bull_prob, bear_prob, signal_display 等
    recent_klines : list[dict], optional
        近期 K 线数据，每条包含 date, close, change, volume
    indicators : dict, optional
        关键技术指标快照，如 {"RSI_14": 58.3, "MACD": 0.0012, ...}

    Returns
    -------
    str or None
        LLM 生成的分析文本，失败时返回 None
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.info("未配置 GEMINI_API_KEY，跳过 LLM 分析")
        return None

    # 构建 User Prompt
    user_prompt = USER_PROMPT_TEMPLATE.format(
        date=signal_data.get("date", ""),
        price=signal_data.get("price", 0),
        bull_prob=signal_data.get("bull_prob", 0),
        bear_prob=signal_data.get("bear_prob", 0),
        signal_display=signal_data.get("signal_display", ""),
        position_pct=signal_data.get("position_pct", 50),
        kline_table=_format_kline_table(recent_klines or []),
        indicators=_format_indicators(indicators or {}),
    )

    logger.info("📝 调用 Gemini 生成策略分析...")
    analysis = _call_gemini(SYSTEM_PROMPT, user_prompt, api_key)

    if analysis:
        logger.info("✅ LLM 分析生成成功 (%d 字)", len(analysis))
    else:
        logger.warning("⚠️ LLM 分析生成失败，将跳过")

    return analysis
