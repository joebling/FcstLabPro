#!/usr/bin/env python3
"""FcstLabPro 生产模型线上推理脚本.

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
from datetime import date, datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 训推共用的特征契约 (Phase 3): build + 列序校验逻辑收敛于此
from src.serving.feature_contract import (  # noqa: E402
    build_feature_frame,
    validate_feature_cols,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M",
)
logger = logging.getLogger("live_signal")

# ----- 默认路径 (从 active.yaml 解析, 不再硬编码模型名) -----
# 历史上这里写死 e1-conservative；现在统一走 src/serving/active_config。
# 仍保留 --model/--config 显式覆盖 (docker_entrypoint 在用)。
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
    run_count_today: int = 0  # 今日已运行次数 (同日重跑计数, 跨日重置)
    last_reason: str | None = None
    last_regime: str | None = None
    last_regime_detail: str | None = None
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
    """拉取最新数据，确保足够的历史窗口用于计算特征.

    读取优先级 (lesson_0602 整改收尾):
      1. data/live/ 实时下载落点 — 生产 pipeline stage 1 刚写的新数据
      2. config 里的 data/raw/ 基准 — 离线/未跑下载时的兑底 (可能过期)
      3. 在线拉取 Binance

    为什么不直接用 config 的 data/raw/: 那是 sha 锁定的训练基准, 生产不会
    更新它 (downloader 拒绝覆盖)。live 链必须吃 data/live/ 的新数据,
    否则就是「下载写 live, 推理读 raw」的路径分裂 (这正是 freshness gate 报警的根因)。
    """
    from src.data.loader import load_csv
    from src.serving.paths import LIVE_OHLCV_PATH

    # 1. 优先用 data/live/ 实时数据 (生产 pipeline 刚下载的)
    if LIVE_OHLCV_PATH.exists():
        logger.info(f"使用实时数据 (data/live): {LIVE_OHLCV_PATH}")
        df = load_csv(str(LIVE_OHLCV_PATH))
        logger.info(f"数据加载完成: {len(df)} 行, {df.index[0].date()} ~ {df.index[-1].date()}")
        return df

    # 2. 回退 config 里的本地基准 (离线环境 / Binance API 不可用)
    local_path = config["data"].get("path")
    if local_path and Path(PROJECT_ROOT / local_path).exists():
        logger.info(f"使用本地基准数据: {local_path}")
        df = load_csv(str(PROJECT_ROOT / local_path))
        logger.info(f"数据加载完成: {len(df)} 行, {df.index[0].date()} ~ {df.index[-1].date()}")
        return df

    # 3. 尝试在线拉取
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

def _days_held(entry_date: str | None, today: str) -> int:
    """持仓天数 = 日历差 (today - entry_date), 而非「跑了几次」的累加。

    这是同日重跑幂等性的基石: 一天内跑 N 次, (today-entry).days 不变,
    不再出现「跑 3 次就以为过了 3 天」的 bug。entry_date 缺失返回 0。
    """
    if not entry_date:
        return 0
    return (date.fromisoformat(today) - date.fromisoformat(entry_date)).days


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
        "regime_detail": "",
        "model_pred": None,
        "reason": "",
    }

    # --- Step 1: Regime ---
    if use_regime:
        bear = is_bear_market(df["close"])
        meta["regime"] = "熊市" if bear else "非熊市"
        # 记录 regime 详情
        if len(df["close"]) >= 64:
            rolling_ret = (df["close"].iloc[-1] / df["close"].iloc[-64]) - 1
            meta["regime_detail"] = f"63d 滚动收益 = {rolling_ret:+.1%} (threshold=-10%)"
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
        days = _days_held(state.entry_date, meta["date"])
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
    # 保留 DataFrame (含列名), 让 LightGBM 双保险校验列名一致:
    # 上游 validate_feature_cols() 已校过顺序, 这里不转 .values 能消除
    # "X does not have valid feature names" 警告 + 防未来重构静默错位。
    X_today = df[feature_cols].iloc[[-1]]
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


def print_signal(signal: str, meta: dict, state: PositionState, model_name: str) -> None:
    """Pretty-print the signal."""
    emoji = SIGNAL_EMOJI.get(signal, "❓")
    display_name = model_name.replace("-", " ").title()
    print("\n" + "=" * 60)
    print(f"  {emoji}  {display_name} 策略信号: {signal}")
    print("=" * 60)
    print(f"  日期:     {meta['date']}")
    print(f"  价格:     ${meta['price']:,.2f}")
    print(f"  Regime:  {meta['regime']}")
    print(f"  原因:     {meta['reason']}")
    if state.in_position and signal in ("HOLD", "SELL"):
        pnl = (meta["price"] - state.entry_price) / state.entry_price
        print(f"  买入价:   ${state.entry_price:,.2f} ({state.entry_date})")
        print(f"  浮盈:     {pnl:+.2%}")
        print(f"  持仓:     {_days_held(state.entry_date, meta['date'])} 天")
    print("=" * 60)


# =====================================================================
# Reusable core (pipeline + CLI 共用, 消除 main 里的过程式重复)
# =====================================================================

def run_signal(
    model_path: Path,
    config_path: Path,
    *,
    state_path: Path,
    use_tp: bool,
    use_regime: bool,
    dry_run: bool = False,
    ledger_mode: str = "live",
) -> tuple[str, dict]:
    """完整跑一次信号: 加载→拉数→特征→校验→信号→落状态→账本.

    pipeline (run_production_pipeline) 与 CLI main() 都走这里, 保证行为一致。
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    logger.info(f"加载模型: {model_path}")
    model = joblib.load(model_path)

    state = PositionState.load(state_path)
    if state.in_position:
        logger.info(f"当前持仓: 买入于 {state.entry_date} @ ${state.entry_price:,.2f}, "
                    f"已持有 {state.days_held} 天")

    df = fetch_latest_data(config)
    df, feature_cols = build_feature_frame(df, config)
    logger.info(f"特征构建完成: {len(feature_cols)} 个特征")
    validate_feature_cols(feature_cols, model_path)

    variant = "基础"
    if use_tp and use_regime:
        variant = "止盈+regime"
    elif use_tp:
        variant = "+止盈"
    elif use_regime:
        variant = "+regime"
    logger.info(f"策略变体: {variant}")

    signal, meta = generate_signal(
        model=model, df=df, feature_cols=feature_cols, state=state,
        config=config, use_tp=use_tp, use_regime=use_regime,
    )

    # 同日重跑计数: 今日第几次跑 (跨日重置)。
    # 策略: 重跑仍发邮件 (你能确认每次跑都成功), 但标上「第 N 次」记号;
    # 持仓天数按日期算 (不受次数影响), 重跑多少次都不会虚增天数。
    is_rerun = bool(state.last_signal_date == meta["date"])
    if is_rerun:
        state.run_count_today += 1
    else:
        state.run_count_today = 1
    meta["is_rerun"] = is_rerun
    meta["run_count_today"] = state.run_count_today
    if is_rerun:
        logger.info(
            f"ℹ️ 今日 ({meta['date']}) 第 {state.run_count_today} 次运行 "
            f"(重跑, 持仓天数不受影响)。"
        )

    _apply_signal_to_state(state, signal, meta)
    print_signal(signal, meta, state, model_path.parent.name)

    if not dry_run:
        state.save(state_path)
        logger.info(f"状态已保存: {state_path}")
    else:
        logger.info("干跑模式，未保存状态")

    _record_to_ledger(
        signal=signal, meta=meta, model_path=model_path,
        df=df, feature_cols=feature_cols,
        ledger_mode="dry-run" if dry_run else ledger_mode,
    )
    return signal, meta


def run_for_model(
    model,
    *,
    state_path: Path,
    ledger_mode: str = "live",
    dry_run: bool = False,
) -> tuple[str, dict]:
    """按 ActiveModel (active.yaml 槽位) 跑信号. variant flags 从 model 解析.

    pipeline 的 4.signals stage 用这个: 模型路径/配置/variant 全部来自 active.yaml,
    无需手工拼 CLI flags。
    """
    flags = set(model.cli_flags)
    return run_signal(
        model.model_path, model.config_path,
        state_path=state_path,
        use_tp="--take-profit" in flags,
        use_regime="--regime-switch" in flags,
        dry_run=dry_run,
        ledger_mode=ledger_mode,
    )


def _apply_signal_to_state(state: PositionState, signal: str, meta: dict) -> None:
    """根据信号更新持仓状态 (BUY 建仓 / SELL 平仓 / HOLD 计天).

    days_held 一律由日期差派生 (today - entry_date), 不再 += 累加。
    保证同一天重跑多次不会虚增天数 (幂等)。
    """
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
            "days_held": _days_held(state.entry_date, today_str),
            "reason": meta["reason"],
        })
        state.in_position = False
        state.entry_date = None
        state.entry_price = None
        state.days_held = 0
    elif signal == "HOLD":
        state.days_held = _days_held(state.entry_date, today_str)

    state.last_signal_date = today_str
    state.last_signal = signal
    state.last_reason = meta.get("reason", "")
    state.last_regime = meta.get("regime", "未知")
    state.last_regime_detail = meta.get("regime_detail", "")


# =====================================================================
# Main
# =====================================================================

def main():
    parser = argparse.ArgumentParser(description="FcstLabPro 线上信号")
    parser.add_argument("--model", default=None,
                        help="模型文件 (不传则从 active.yaml 解析)")
    parser.add_argument("--config", default=None,
                        help="实验配置 (不传则从 active.yaml 解析)")
    parser.add_argument("--model-slot", default=None,
                        help="active.yaml 槽位名或模型名 (primary/challenger/e1-conservative)，"
                             "默认 primary。仅在未显式传 --model 时生效")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="状态文件")
    parser.add_argument("--take-profit", action="store_true", help="启用止盈 (稳健版)")
    parser.add_argument("--regime-switch", action="store_true", help="启用 regime 开关 (保守版)")
    parser.add_argument("--dry-run", action="store_true", help="干跑模式，不更新状态")
    parser.add_argument("--ledger-mode", default="live",
                        choices=["live", "shadow", "dry-run"],
                        help="信号账本写入模式 (live=写live+archive, shadow=只archive)")
    args = parser.parse_args()

    # 解析模型路径: 显式 --model 优先, 否则从 active.yaml
    if args.model and args.config:
        model_path = Path(args.model)
        config_path = Path(args.config)
    else:
        from src.serving import resolve_model
        active = resolve_model(args.model_slot)
        model_path = Path(args.model) if args.model else active.model_path
        config_path = Path(args.config) if args.config else active.config_path
        logger.info(f"从 active.yaml 解析模型: {active.slot}={active.name} "
                    f"(variant={active.strategy_variant}, status={active.status})")

    # 全部过程收敛到 run_signal (pipeline 与 CLI 共用, 消除 DRY 违规)
    signal, meta = run_signal(
        model_path, config_path,
        state_path=Path(args.state),
        use_tp=args.take_profit,
        use_regime=args.regime_switch,
        dry_run=args.dry_run,
        ledger_mode=args.ledger_mode,
    )
    return signal, meta


def _record_to_ledger(signal, meta, model_path, df, feature_cols, ledger_mode):
    """把信号写入 live/shadow/archive 账本 + 生成监控产物."""
    from src.serving.signal_ledger import record_signal, write_monitoring

    model_dir = model_path.parent
    model_name = model_dir.name

    # 模型谱系: hash 从 manifest, variant 从 active.yaml, fc_sha 从 feature_cols.json
    model_hash = variant = fc_sha = None
    manifest_p = model_dir / "manifest.json"
    if manifest_p.exists():
        mf = json.loads(manifest_p.read_text())
        model_hash = mf.get("model", {}).get("sha256_prefix")
        variant = mf.get("deployment", {}).get("variant")
    fc_p = model_dir / "feature_cols.json"
    if fc_p.exists():
        fc_sha = json.loads(fc_p.read_text()).get("sha256")

    data_last = meta.get("date", "")
    try:
        record_signal(
            {"date": data_last, "price": meta.get("price"),
             "signal": signal, "regime": meta.get("regime"),
             "reason": meta.get("reason")},
            model_name=model_name, model_hash=model_hash or "unknown",
            variant=variant or "unknown", input_data_end=data_last,
            mode=ledger_mode, feature_cols_sha256=fc_sha,
        )
        write_monitoring(
            model_name=model_name, n_rows=len(df),
            data_last_date=data_last, signal=signal,
            probability=meta.get("probability"),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"信号账本写入失败 (不阻断信号): {e}")


if __name__ == "__main__":
    main()
