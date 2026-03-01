#!/usr/bin/env python3
"""E1 策略线上推理脚本.

每日运行一次，输出买入/持有/平仓/静默信号。

Usage:
    # 基础版 (激进)
    python scripts/live_signal.py

    # +止盈 (稳健)
    python scripts/live_signal.py --take-profit

    # +止盈+regime (保守)
    python scripts/live_signal.py --take-profit --regime-switch

    # 干跑 (dry-run)，不更新状态文件
    python scripts/live_signal.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M",
)
logger = logging.getLogger("live_signal")

# ----- 默认路径 -----
DEFAULT_MODEL = PROJECT_ROOT / "experiments/weekly/weekly_bear_v0305_E1_decontam/model.joblib"
DEFAULT_CONFIG = PROJECT_ROOT / "experiments/weekly/weekly_bear_v0305_E1_decontam/config.yaml"
DEFAULT_STATE = PROJECT_ROOT / "data/live/signal_state.json"


# =====================================================================
# Position State
# =====================================================================

@dataclass
class PositionState:
    """Persistent position tracking."""
    in_position: bool = False
    entry_date: str | None = None
    entry_price: float | None = None
    days_held: int = 0
    last_signal_date: str | None = None
    last_signal: str | None = None
    history: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "PositionState":
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)


# =====================================================================
# Data Pipeline
# =====================================================================

def fetch_latest_data(config: dict) -> pd.DataFrame:
    """拉取最新数据，确保足够的历史窗口用于计算特征."""
    from src.data.loader import load_csv

    # 优先用本地数据 (离线环境 / Binance API 不可用)
    local_path = config["data"].get("path")
    if local_path and Path(PROJECT_ROOT / local_path).exists():
        logger.info(f"使用本地数据: {local_path}")
        df = load_csv(str(PROJECT_ROOT / local_path))
        logger.info(f"数据加载完成: {len(df)} 行, {df.index[0].date()} ~ {df.index[-1].date()}")
        return df

    # 尝试在线拉取
    try:
        from src.data.downloader import download_binance_klines
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = (datetime.utcnow() - timedelta(days=400)).strftime("%Y-%m-%d")
        symbol = config["data"].get("symbol", "BTCUSDT")
        logger.info(f"拉取 {symbol} 日线数据: {start_date} ~ {end_date}")
        df = download_binance_klines(symbol=symbol, interval="1d", start=start_date, end=end_date)
        df.index.name = "date"
        logger.info(f"数据拉取完成: {len(df)} 行")
        return df
    except Exception as e:
        logger.error(f"数据拉取失败: {e}")
        raise


def prepare_features(df: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, list[str]]:
    """构建特征，返回 (df, feature_cols)."""
    from src.features.builder import build_features, get_feature_columns

    feat_cfg = config["features"]
    df = build_features(
        df,
        feature_sets=feat_cfg["sets"],
        drop_na_method=feat_cfg.get("drop_na_method", "ffill_then_drop"),
        drop_features=feat_cfg.get("drop_features"),
    )
    feature_cols = get_feature_columns(df)
    return df, feature_cols


# =====================================================================
# Regime Detection
# =====================================================================

def is_bear_market(prices: pd.Series, window: int = 63, threshold: float = -0.10) -> bool:
    """判断当前是否熊市.

    规则: 滚动 63 天收益率 ≤ -10% → 熊市
    """
    if len(prices) < window + 1:
        logger.warning(f"价格序列不足 {window+1} 天，无法判断 regime")
        return False
    rolling_ret = (prices.iloc[-1] / prices.iloc[-window - 1]) - 1
    logger.info(f"Regime: 63d 滚动收益 = {rolling_ret:.2%} (threshold={threshold:.0%})")
    return rolling_ret <= threshold


# =====================================================================
# Signal Logic
# =====================================================================

def generate_signal(
    model,
    df: pd.DataFrame,
    feature_cols: list[str],
    state: PositionState,
    config: dict,
    use_tp: bool = False,
    use_regime: bool = False,
) -> tuple[str, dict]:
    """生成交易信号.

    Returns
    -------
    (signal, metadata)
    signal ∈ {"BUY", "HOLD", "SELL", "SILENT"}
    """
    label_cfg = config["label"]
    T = label_cfg.get("T", 21)
    X = label_cfg.get("X", 0.04)
    today = df.index[-1]
    current_price = float(df["close"].iloc[-1])

    meta = {
        "date": str(today.date()),
        "price": current_price,
        "regime": "unknown",
        "model_pred": None,
        "reason": "",
    }

    # --- Step 1: Regime ---
    if use_regime:
        bear = is_bear_market(df["close"])
        meta["regime"] = "熊市" if bear else "非熊市"
        if bear:
            # 熊市: 如果有持仓，强制平仓
            if state.in_position:
                meta["reason"] = f"regime=熊市, 强制平仓 (63d收益≤-10%)"
                return "SELL", meta
            meta["reason"] = "regime=熊市, 策略静默"
            return "SILENT", meta
    else:
        meta["regime"] = "N/A (未启用)"

    # --- Step 2: 如果已持仓，检查退出条件 ---
    if state.in_position:
        days = state.days_held + 1
        pnl = (current_price - state.entry_price) / state.entry_price

        # 止盈触发
        if use_tp and pnl >= X:
            meta["reason"] = f"止盈触发: PnL={pnl:.2%} ≥ {X:.0%}, 持仓{days}天"
            return "SELL", meta

        # 时间触发
        if days >= T:
            meta["reason"] = f"到期平仓: 持仓{days}天 ≥ T={T}, PnL={pnl:.2%}"
            return "SELL", meta

        # 继续持有
        meta["reason"] = f"继续持有: 第{days}天/{T}天, PnL={pnl:.2%}"
        return "HOLD", meta

    # --- Step 3: 模型预测 ---
    X_today = df[feature_cols].iloc[[-1]].values
    y_pred = int(model.predict(X_today)[0])
    meta["model_pred"] = y_pred

    if y_pred == 1:
        meta["reason"] = "模型信号: y_pred=1 (预测跌后反弹)"
        return "BUY", meta

    meta["reason"] = "无信号: y_pred=0"
    return "SILENT", meta


# =====================================================================
# Output
# =====================================================================

SIGNAL_EMOJI = {
    "BUY": "🟢", "SELL": "🔴", "HOLD": "🟡", "SILENT": "⚪",
}


def print_signal(signal: str, meta: dict, state: PositionState) -> None:
    """Pretty-print the signal."""
    emoji = SIGNAL_EMOJI.get(signal, "❓")
    print("\n" + "=" * 60)
    print(f"  {emoji}  E1 策略信号: {signal}")
    print("=" * 60)
    print(f"  日期:     {meta['date']}")
    print(f"  价格:     ${meta['price']:,.2f}")
    print(f"  Regime:  {meta['regime']}")
    print(f"  原因:     {meta['reason']}")
    if state.in_position and signal in ("HOLD", "SELL"):
        pnl = (meta["price"] - state.entry_price) / state.entry_price
        print(f"  买入价:   ${state.entry_price:,.2f} ({state.entry_date})")
        print(f"  浮盈:     {pnl:+.2%}")
        print(f"  持仓:     {state.days_held + 1} 天")
    print("=" * 60)


# =====================================================================
# Main
# =====================================================================

def main():
    parser = argparse.ArgumentParser(description="E1 策略线上信号")
    parser.add_argument("--model", default=str(DEFAULT_MODEL), help="模型文件")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="实验配置")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="状态文件")
    parser.add_argument("--take-profit", action="store_true", help="启用止盈 (稳健版)")
    parser.add_argument("--regime-switch", action="store_true", help="启用 regime 开关 (保守版)")
    parser.add_argument("--dry-run", action="store_true", help="干跑模式，不更新状态")
    args = parser.parse_args()

    # 加载配置
    with open(args.config) as f:
        config = yaml.safe_load(f)

    # 加载模型
    logger.info(f"加载模型: {args.model}")
    model = joblib.load(args.model)

    # 加载状态
    state_path = Path(args.state)
    state = PositionState.load(state_path)
    if state.in_position:
        logger.info(f"当前持仓: 买入于 {state.entry_date} @ ${state.entry_price:,.2f}, "
                    f"已持有 {state.days_held} 天")

    # 拉取数据
    df = fetch_latest_data(config)

    # 构建特征
    df, feature_cols = prepare_features(df, config)
    logger.info(f"特征构建完成: {len(feature_cols)} 个特征")

    # 生成信号
    variant = "基础"
    if args.take_profit and args.regime_switch:
        variant = "止盈+regime"
    elif args.take_profit:
        variant = "+止盈"
    elif args.regime_switch:
        variant = "+regime"
    logger.info(f"策略变体: {variant}")

    signal, meta = generate_signal(
        model=model, df=df, feature_cols=feature_cols, state=state,
        config=config, use_tp=args.take_profit, use_regime=args.regime_switch,
    )

    # 更新状态
    today_str = meta["date"]
    if signal == "BUY" and not state.in_position:
        state.in_position = True
        state.entry_date = today_str
        state.entry_price = meta["price"]
        state.days_held = 0
    elif signal == "SELL" and state.in_position:
        pnl = (meta["price"] - state.entry_price) / state.entry_price
        state.history.append({
            "entry_date": state.entry_date,
            "exit_date": today_str,
            "entry_price": state.entry_price,
            "exit_price": meta["price"],
            "pnl": round(pnl, 4),
            "days_held": state.days_held + 1,
            "reason": meta["reason"],
        })
        state.in_position = False
        state.entry_date = None
        state.entry_price = None
        state.days_held = 0
    elif signal == "HOLD":
        state.days_held += 1

    state.last_signal_date = today_str
    state.last_signal = signal

    # 输出
    print_signal(signal, meta, state)

    # 保存状态
    if not args.dry_run:
        state.save(state_path)
        logger.info(f"状态已保存: {state_path}")
    else:
        logger.info("干跑模式，未保存状态")

    # 返回信号以供外部集成
    return signal, meta


if __name__ == "__main__":
    main()
