"""LLM 策略分析师 — 多 provider 可配置, 对模型信号做智能解读.

结合模型输出、近期 K 线、历史战绩, 生成自然语言策略解读, 嵌入每日信号邮件。

Provider 通过环境变量选择 (零硬编码 key):

    LLM_PROVIDER=gemini  (默认, 向后兼容)
      GEMINI_API_KEY    Google AI API Key
      GEMINI_MODEL      默认 gemini-2.0-flash

LLM_PROVIDER=anthropic  (Anthropic Messages API 格式, 含腾讯 tokenhub 网关)
      LLM_API_KEY       API Key (或复用 ANTHROPIC_API_KEY)
      LLM_BASE_URL      网关地址, 如 https://tokenhub.tencentmaas.com/
      LLM_MODEL         模型名, 如 deepseek-v4-pro

    LLM_PROVIDER=deepseek  (OpenAI 兼容 Chat Completions 格式, 官方 platform.deepseek.com)
      DEEPSEEK_API_KEY  API Key (或复用 LLM_API_KEY)
      LLM_BASE_URL      默认 https://api.deepseek.com
      LLM_MODEL         默认 deepseek-chat

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

### 特征集来源
- **technical**: SMA/EMA/MACD/BB/ATR/动量 (已移除 RSI/SMA 避免与标签泄漏)
- **volume**: 成交量均线、量比、OBV、VWAP
- **flow**: 资金流向代理指标
- **market_structure**: 模拟资金费率、CVD、量价背离
- **external_fgi**: Fear & Greed Index 及其移动平均

⚠️ 不包含：链上数据、新闻/社交媒体、宏观经济指标、基本面数据
注意: 本次解读的模型具体特征数 / Kappa / 回测指标见下方「当前模型档案」，
以那里的真实数值为准 (不同模型差异很大, 不要臆测固定数字)。

### 你的分析原则
1. 模型预测力有限 (以「当前模型档案」的 Kappa 为准)，永远提醒用户风险
2. 结合近期 K 线走势判断技术面以外的驱动因素
3. 如果提供了历史战绩，分析胜负模式（哪种退出方式胜率高、哪种市场条件下表现好）
4. 如果有当前持仓，重点分析持仓风险和潜在退出时机
5. 不要重复原始数据，直接给出分析判断
"""

USER_PROMPT_TEMPLATE = """以下是今日的预测信号和近期走势数据，请给出分析。

## 当前模型档案 (以此为准, 勿臆测)
{model_context}

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


def _format_model_context(model: dict) -> str:
    """从 signal JSON 的 model 字段提凖真实模型画像, 注入 prompt.

    这部分是为了让 LLM 拿到本次模型的**真实** Kappa / 特征数 / 回测指标,
    而不是 System Prompt 里的通用描述 (不同模型差异很大)。model 缺失时回退提示。
    """
    if not model:
        return "（未提供模型档案, 请以保守态度评估预测力）"
    bt = model.get("backtest", {}) or {}
    lines = [
        f"- 模型: {model.get('name', 'N/A')} ({model.get('raw_name', '')})",
        f"- 类型/标签: {model.get('type', 'N/A')} / {model.get('label', 'N/A')}",
        f"- 策略变体: {model.get('variant', 'N/A')}",
        f"- 特征数: {model.get('features', 'N/A')} 个 (剩枝后)",
        f"- Cohen's Kappa: {model.get('kappa', 'N/A')} (越高越可靠, 低于 0.2 接近噪音)",
    ]
    if bt:
        lines.append(
            f"- 该变体回测: CAGR={bt.get('cagr', 'N/A')}, "
            f"MaxDD={bt.get('max_dd', 'N/A')}, "
            f"Sharpe={bt.get('sharpe', 'N/A')}, "
            f"PF={bt.get('pf', 'N/A')}"
        )
    return "\n".join(lines)


# ── Providers ──

def _http_post_json(url, payload, headers, timeout=60):
    """通用 POST JSON (urllib, 无额外依赖). 返回解析后 dict 或 None."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        logger.error("LLM API HTTP 错误 %d: %s", e.code, body[:300])
        return None
    except Exception as e:  # noqa: BLE001
        logger.error("LLM API 调用失败: %s", e)
        return None


def _resolve_provider():
    """从环境变量解析 provider 配置. 返回 (provider, cfg) 或 (None, None)."""
    provider = os.environ.get("LLM_PROVIDER", "gemini").strip().lower()

    if provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            return None, None
        return "gemini", {
            "api_key": api_key,
            "model": os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
        }

    if provider in ("anthropic", "custom_anthropic"):
        api_key = (
            os.environ.get("LLM_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or ""
        ).strip()
        if not api_key:
            return None, None
        return "anthropic", {
            "api_key": api_key,
            "base_url": os.environ.get("LLM_BASE_URL", "https://api.anthropic.com"),
            "model": os.environ.get("LLM_MODEL", "claude-3-5-sonnet-latest"),
        }

    if provider in ("deepseek", "openai"):
        # OpenAI 兼容 Chat Completions 格式 (官方 DeepSeek / 任意 OpenAI 兼容网关)
        api_key = (
            os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        ).strip()
        if not api_key:
            return None, None
        _default_base = (
            "https://api.deepseek.com" if provider == "deepseek"
            else "https://api.openai.com"
        )
        _default_model = "deepseek-chat" if provider == "deepseek" else "gpt-4o-mini"
        return "openai", {
            "api_key": api_key,
            "base_url": os.environ.get("LLM_BASE_URL", _default_base),
            "model": os.environ.get("LLM_MODEL", _default_model),
        }

    logger.warning("未知 LLM_PROVIDER=%s, 跳过 LLM 分析", provider)
    return None, None


def _call_gemini(system_prompt, user_prompt, cfg):
    """调用 Gemini API（使用 urllib，无需额外依赖）."""
    model = cfg.get("model", "gemini-2.0-flash")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={cfg['api_key']}"
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
    headers = {"Content-Type": "application/json"}
    result = _http_post_json(url, payload, headers, timeout=30)
    if not result:
        return None
    candidates = result.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        if parts:
            return parts[0].get("text", "")
    logger.warning(
        "Gemini 返回无内容: %s", json.dumps(result, ensure_ascii=False)[:200]
    )
    return None


def _call_openai(system_prompt, user_prompt, cfg):
    """调用 OpenAI 兼容 Chat Completions API (官方 DeepSeek / 任意兼容网关)."""
    base = (cfg.get("base_url") or "https://api.deepseek.com").rstrip("/")
    url = f"{base}/v1/chat/completions"
    payload = {
        "model": cfg.get("model", "deepseek-chat"),
        "max_tokens": 800,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    result = _http_post_json(url, payload, headers)
    if not result:
        return None
    choices = result.get("choices", [])
    if choices:
        msg = choices[0].get("message", {})
        text = msg.get("content", "")
        if text:
            return text
    logger.warning(
        "OpenAI 兼容 API 返回无内容: %s",
        json.dumps(result, ensure_ascii=False)[:200],
    )
    return None



def _call_anthropic(system_prompt, user_prompt, cfg):
    """调用 Anthropic Messages API 格式 (含腾讯 tokenhub 等兼容网关)."""
    base = (cfg.get("base_url") or "https://api.anthropic.com").rstrip("/")
    url = f"{base}/v1/messages"
    payload = {
        "model": cfg.get("model", "claude-3-5-sonnet-latest"),
        "max_tokens": 800,
        "temperature": 0.7,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": cfg["api_key"],
        "authorization": f"Bearer {cfg['api_key']}",
        "anthropic-version": "2023-06-01",
    }
    result = _http_post_json(url, payload, headers)
    if not result:
        return None
    content = result.get("content", [])
    if isinstance(content, list):
        texts = [
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        if texts:
            return "".join(texts)
    logger.warning(
        "Anthropic 返回无内容: %s", json.dumps(result, ensure_ascii=False)[:200]
    )
    return None


_DISPATCH = {
    "gemini": _call_gemini,
    "anthropic": _call_anthropic,
    "openai": _call_openai,
}


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
    provider, cfg = _resolve_provider()
    if not provider:
        logger.info("未配置 LLM provider/key，跳过 LLM 分析")
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
        model_context=_format_model_context(signal_data.get("model", {})),
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

    logger.info("📝 调用 %s (%s) 生成策略分析...", provider, cfg.get("model"))
    analysis = _DISPATCH[provider](SYSTEM_PROMPT, user_prompt, cfg)

    if analysis:
        logger.info("✅ LLM 分析生成成功 (%d 字)", len(analysis))
    else:
        logger.warning("⚠️ LLM 分析生成失败，将跳过")

    return analysis
