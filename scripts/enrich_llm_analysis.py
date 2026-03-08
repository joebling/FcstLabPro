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


def main(signal_path: str) -> None:
    with open(signal_path) as f:
        data = json.load(f)

    try:
        from src.llm.analyst import generate_analysis
        import pandas as pd

        data_file = Path("data/raw/btc_binance_BTCUSDT_1d.csv")
        # Docker 环境
        if Path("/app/data/raw/btc_binance_BTCUSDT_1d.csv").exists():
            data_file = Path("/app/data/raw/btc_binance_BTCUSDT_1d.csv")

        df = pd.read_csv(str(data_file), index_col=0).sort_index()
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

        analysis = generate_analysis(
            data,
            klines,
            {},
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
