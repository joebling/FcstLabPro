#!/usr/bin/env python3
"""给信号 JSON 注入 LLM 分析.

读取信号 JSON 和近期 K 线数据，调用 Gemini 生成策略分析，
写回原 JSON 文件的 llm_analysis 字段。

Usage:
    python scripts/enrich_llm_analysis.py /tmp/signals/signal_2026-03-08.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# OHLCV 走 serving 单一真相源 (data/live/) — 与推理/freshness gate 同源。
# 锁定到项目根, 不依赖 cwd (修复 cron 从 /opt/fcstlabpro 启动时裸相对路径找不到 OHLCV)。
from src.serving.paths import LIVE_OHLCV_PATH as OHLCV_PATH


def _compute_indicators(df) -> dict:
    """从 OHLCV 算出当前关键技术指标快照, 喞 LLM 做定量判断。

    只算轻量、解读性强的指标 (SMA/RSI/波动率/量比/位置),
    避免依赖完整特征工程 (那是推理链的事)。数据不足时跳过该项。
    """
    import numpy as np

    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    out: dict = {}
    last = float(close.iloc[-1])

    # 均线 + 价格相对位置
    for w in (20, 50, 200):
        if len(close) >= w:
            sma = float(close.tail(w).mean())
            out[f"SMA{w}"] = round(sma, 2)
            out[f"价格 vs SMA{w}"] = f"{(last / sma - 1) * 100:+.1f}%"

    # RSI(14) — 标准 Wilder 均值
    if len(close) >= 15:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - 100 / (1 + rs)
        if not np.isnan(rsi.iloc[-1]):
            out["RSI14"] = round(float(rsi.iloc[-1]), 1)

    # 近期收益 + 年化波动率
    if len(close) >= 8:
        out["7日收益"] = f"{(last / float(close.iloc[-8]) - 1) * 100:+.1f}%"
    if len(close) >= 64:
        out["63日收益"] = f"{(last / float(close.iloc[-64]) - 1) * 100:+.1f}%"
    if len(close) >= 21:
        daily_ret = close.pct_change().tail(20)
        out["20日年化波动率"] = f"{float(daily_ret.std()) * (365 ** 0.5) * 100:.0f}%"

    # 成交量比 (当日 vs 20日均量)
    if len(vol) >= 20:
        vma = float(vol.tail(20).mean())
        if vma > 0:
            out["量比(vs 20日均)"] = f"{float(vol.iloc[-1]) / vma:.2f}x"

    return out


def main(signal_path: str) -> None:
    with open(signal_path) as f:
        data = json.load(f)

    try:
        from src.llm.analyst import generate_analysis
        import pandas as pd

        df = pd.read_csv(str(OHLCV_PATH), index_col=0).sort_index()
        recent = df.tail(7)
        klines = [
            {
                "date": str(idx)[:10],
                "close": float(r["close"]),
                "volume": float(r["volume"]),
                "change": float(
                    (r["close"] - df["close"].shift(1).loc[idx]) / df["close"].shift(1).loc[idx] * 100
                ) if idx != df.index[0] else 0.0,
            }
            for idx, r in recent.iterrows()
        ]

        indicators = _compute_indicators(df)

        analysis = generate_analysis(
            data,
            klines,
            indicators,
            trade_history=data.get("history"),
            position=data.get("position"),
        )

        if analysis:
            data["llm_analysis"] = analysis
            with open(signal_path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"✅ LLM 分析已添加 ({len(analysis)} 字)")
        else:
            print("⚠️ LLM 分析返回空")

    except Exception as e:
        print(f"⚠️ LLM 分析出错: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/enrich_llm_analysis.py <signal_json_path>")
        sys.exit(1)
    main(sys.argv[1])
