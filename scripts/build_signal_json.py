#!/usr/bin/env python3
"""从 state + manifest 生成模型无关的信号 JSON.

读取 manifest.json 中的模型元信息，不硬编码任何模型特定内容。

Usage:
    python scripts/build_signal_json.py \
        --model-dir models/production/e1-conservative \
        --state-file /tmp/state/signal_state.json \
        --variant conservative \
        --output-dir /tmp/signals
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _parse_model_info(manifest: dict, variant: str) -> dict:
    """从 manifest.json 提取模型信息."""
    strategy = manifest.get("strategy", {})
    classification = manifest.get("metrics", {}).get("classification", {})

    # 根据 variant 选择对应的 PnL 回测指标
    pnl_key_map = {
        "conservative": "策略(止盈+regime)",
        "moderate": "策略(+止盈)",
        "base": "策略(无开关)",
    }
    pnl_key = pnl_key_map.get(variant, "策略(止盈+regime)")
    pnl = manifest.get("metrics", {}).get("pnl", {}).get(pnl_key, {})

    # 模型名: "e1-conservative" → "E1 Conservative"
    raw_name = manifest.get("name", "unknown")
    display_name = raw_name.replace("-", " ").title()

    # 版本: 从实验名提取
    exp_id = manifest.get("source_experiment", {}).get("id", "")
    version = "v0305"  # default
    if "_v" in exp_id:
        version = "v" + exp_id.split("_v")[-1][:4]

    # 特征数: "129 (after decontamination)" → 129
    feat_count_raw = str(manifest.get("features", {}).get("count", "129"))
    feat_count = int(feat_count_raw.split()[0])

    model_type = manifest.get("model", {}).get("type", "lightgbm")
    if model_type.lower() == "lightgbm":
        model_type = "LightGBM"

    return {
        "name": display_name,
        "raw_name": raw_name,
        "version": version,
        "type": model_type,
        "label": strategy.get("label", "N/A"),
        "features": feat_count,
        "kappa": round(classification.get("cohen_kappa", 0), 2),
        "variant": variant,
        "backtest": {
            "cagr": f"{pnl.get('cagr', 0) * 100:.1f}%",
            "max_dd": f"{pnl.get('max_drawdown', 0) * 100:.1f}%",
            "pf": round(pnl.get("profit_factor", 0), 2),
            "sharpe": round(pnl.get("sharpe", 0), 2),
        },
    }


def _parse_history(raw_history: list[dict]) -> dict:
    """汇总历史交易记录."""
    total = len(raw_history)
    if total == 0:
        return {
            "total_trades": 0, "wins": 0, "win_rate": 0.0,
            "avg_pnl": 0.0, "total_pnl": 0.0, "recent": [], "exit_stats": {},
        }

    wins = sum(1 for t in raw_history if t.get("pnl", 0) > 0)
    avg_pnl = sum(t.get("pnl", 0) for t in raw_history) / total
    total_pnl = sum(t.get("pnl", 0) for t in raw_history)

    recent = []
    for t in raw_history[-3:]:
        reason_raw = t.get("reason", "")
        reason_short = reason_raw.split(":")[0] if ":" in reason_raw else reason_raw
        recent.append({
            "entry": t.get("entry_date", "")[-5:],
            "exit": t.get("exit_date", "")[-5:],
            "pnl": f"{t.get('pnl', 0):+.1%}",
            "reason": reason_short,
        })

    # 退出方式统计
    exit_stats: dict[str, dict] = {}
    for t in raw_history:
        r = t.get("reason", "其他")
        key = (
            "止盈" if "止盈" in r else
            "到期" if "到期" in r else
            "regime" if "regime" in r else "其他"
        )
        if key not in exit_stats:
            exit_stats[key] = {"count": 0, "wins": 0}
        exit_stats[key]["count"] += 1
        if t.get("pnl", 0) > 0:
            exit_stats[key]["wins"] += 1

    return {
        "total_trades": total,
        "wins": wins,
        "win_rate": round(wins / total, 2),
        "avg_pnl": round(avg_pnl, 4),
        "total_pnl": round(total_pnl, 4),
        "recent": recent,
        "exit_stats": exit_stats,
    }


def build_signal_json(
    model_dir: Path,
    state_file: Path,
    variant: str,
    output_dir: Path,
    data_path: Path | None = None,
) -> Path | None:
    """生成信号 JSON 文件."""
    if not state_file.exists():
        print("⚠️ 状态文件不存在，跳过 JSON 生成")
        return None

    # 读取输入
    with open(state_file) as f:
        state = json.load(f)

    with open(model_dir / "manifest.json") as f:
        manifest = json.load(f)

    # 读取价格
    dp = data_path or Path("data/raw/btc_binance_BTCUSDT_1d.csv")
    if not dp.is_absolute():
        dp = PROJECT_ROOT / dp
    df = pd.read_csv(str(dp), index_col=0).sort_index()
    price = float(df["close"].iloc[-1])
    date_str = state.get("last_signal_date", datetime.utcnow().strftime("%Y-%m-%d"))

    # 信号
    signal = state.get("last_signal", "SILENT")
    signal_map = {
        "BUY": "🟢 买入", "HOLD": "🟡 持有中",
        "SELL": "🔴 卖出", "SILENT": "⚪ 静默",
    }

    # 持仓
    floating_pnl = 0.0
    if state.get("in_position") and state.get("entry_price"):
        floating_pnl = (price - state["entry_price"]) / state["entry_price"]

    position = {
        "in_position": state.get("in_position", False),
        "entry_date": state.get("entry_date"),
        "entry_price": state.get("entry_price"),
        "days_held": state.get("days_held", 0),
        "floating_pnl": round(floating_pnl, 4),
    }

    # 元信息
    strategy = manifest.get("strategy", {})
    model_info = _parse_model_info(manifest, variant)
    history = _parse_history(state.get("history", []))

    signal_data = {
        "date": date_str,
        "price": price,
        "signal": signal,
        "signal_display": signal_map.get(signal, signal),
        "reason": state.get("last_reason", "无"),
        "regime": state.get("last_regime", "未知"),
        "regime_detail": state.get("last_regime_detail", ""),
        "position": position,
        "history": history,
        "model": model_info,
        "strategy": {
            "T": strategy.get("T", 21),
            "X": strategy.get("X", 0.04),
            "take_profit": variant in ("moderate", "conservative"),
            "regime_switch": variant == "conservative",
        },
        "risk_notes": [
            f"策略变体: {variant}",
            f"回测 CAGR={model_info['backtest']['cagr']}, "
            f"MaxDD={model_info['backtest']['max_dd']}, "
            f"PF={model_info['backtest']['pf']}",
        ],
        "llm_analysis": None,
    }

    # 写入
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"signal_{date_str}.json"
    with open(out_path, "w") as f:
        json.dump(signal_data, f, indent=2, ensure_ascii=False)

    print(f"✅ 信号 JSON: {out_path}")
    print(f"   {signal_map.get(signal, signal)} | ${price:,.2f} | {model_info['name']}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成信号 JSON")
    parser.add_argument("--model-dir", required=True, help="模型目录")
    parser.add_argument("--state-file", required=True, help="状态文件")
    parser.add_argument("--variant", default="conservative", help="策略变体")
    parser.add_argument("--output-dir", default="/tmp/signals", help="输出目录")
    args = parser.parse_args()

    build_signal_json(
        model_dir=Path(args.model_dir),
        state_file=Path(args.state_file),
        variant=args.variant,
        output_dir=Path(args.output_dir),
    )
