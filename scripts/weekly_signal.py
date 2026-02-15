#!/usr/bin/env python3
"""每日交易信号 — 基于 v9 Bull/Bear 双模型输出概率化交易建议.

每天运行一次（北京时间 08:00），输出：
  1. Bull/Bear 概率
  2. 综合信号（强多头/强空头/震荡/高波动）
  3. 建议仓位比例
  4. 风控提示

数据源：Binance BTCUSDT 日线 K线（唯一数据源，无需 API Key）
API: https://api.binance.com/api/v3/klines
字段: OHLCV + quote_volume + trades

Usage:
    python scripts/weekly_signal.py
    python scripts/weekly_signal.py --download   # 先下载最新数据再预测
    python scripts/weekly_signal.py --download --save  # 下载 + 保存信号 JSON
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import joblib
import numpy as np
import pandas as pd

from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns
from src.llm.analyst import generate_analysis

# ── 日志配置（Cloud Run 友好） ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── 默认模型路径 (v9) ──
DEFAULT_BULL_DIR = "experiments/weekly/weekly_bull_v9_fgi_v2_20260215_113918_2181e7"
DEFAULT_BEAR_DIR = "experiments/weekly/weekly_bear_v9_fgi_v2_20260215_114152_6c90ee"


def load_model_and_features(exp_dir: str):
    """加载模型、特征配置和元信息（增强容错）."""
    import yaml, json
    exp_path = PROJECT_ROOT / exp_dir
    model = joblib.load(exp_path / "model.joblib")
    
    with open(exp_path / "config.yaml") as f:
        config = yaml.safe_load(f)
    
    # 加载 meta.json 或 metrics.json
    meta = {}
    for meta_file in ["metrics.json", "meta.json"]:
        meta_path = exp_path / meta_file
        if meta_path.exists():
            with open(meta_path) as mf:
                meta = json.load(mf)
            break
    
    # 🔧 增强：从 config 补充缺失字段
    exp_config = config.get("experiment", {})
    
    # 补充 version
    if "version" not in meta:
        meta["version"] = exp_config.get("name", meta.get("name", "unknown"))
    
    # 补充 label_strategy
    if "label_strategy" not in meta:
        label_cfg = config.get("label", {})
        meta["label_strategy"] = label_cfg.get("strategy", "unknown")
    
    # 补充 feature_set
    if "feature_set" not in meta:
        feat_cfg = config.get("features", {})
        meta["feature_set"] = feat_cfg.get("sets", [])
    
    # 补充 kappa
    if "kappa" not in meta:
        kappa = None
        # 优先从 aggregate_metrics 读取
        if "aggregate_metrics" in meta and "cohen_kappa" in meta["aggregate_metrics"]:
            kappa = meta["aggregate_metrics"]["cohen_kappa"]
        # 否则直接从 meta 读取（metrics.json 格式）
        elif "cohen_kappa" in meta:
            kappa = meta["cohen_kappa"]
        # 格式化为 2 位小数
        if kappa is not None:
            kappa = f"{kappa:.2f}"
        meta["kappa"] = kappa if kappa is not None else "N/A"
    
    logger.info(f"[DEBUG] loaded meta for {exp_dir}: version={meta.get('version')}, kappa={meta.get('kappa')}, label_strategy={meta.get('label_strategy')}")
    
    return model, config, meta


def compute_latest_features(config: dict, download: bool = False) -> pd.DataFrame:
    """计算最新一天的特征."""
    data_cfg = config["data"]
    data_path = data_cfg.get("path")

    if download:
        from src.data.downloader import download_binance_klines

        print("📥 下载最新日线数据...")
        df = download_binance_klines(
            symbol=data_cfg.get("symbol", "BTCUSDT"),
            interval=data_cfg.get("interval", "1d"),
            start="2020-01-01",
        )
    else:
        df = load_csv(data_path)

    feat_cfg = config["features"]
    df = build_features(df, feature_sets=feat_cfg["sets"])
    return df


def get_signal_and_advice(
    bull_prob: float,
    bear_prob: float,
    bull_threshold: float = 0.50,
    bear_threshold: float = 0.50,
) -> dict:
    """根据概率输出综合信号和交易建议.

    Parameters
    ----------
    bull_prob : 模型输出的 P(大涨) 概率
    bear_prob : 模型输出的 P(大跌) 概率
    bull_threshold : Bull 判定阈值
    bear_threshold : Bear 判定阈值

    Returns
    -------
    dict : 包含 signal, position, advice, risk_level 等
    """
    bull_on = bull_prob >= bull_threshold
    bear_on = bear_prob >= bear_threshold

    # ── 信号判定 ──
    if bull_on and not bear_on:
        signal = "📈 强多头"
        signal_code = "BULL"
    elif not bull_on and bear_on:
        signal = "📉 强空头"
        signal_code = "BEAR"
    elif not bull_on and not bear_on:
        signal = "⏸️ 震荡"
        signal_code = "NEUTRAL"
    else:
        signal = "⚠️ 高波动"
        signal_code = "VOLATILE"

    # ── 概率强度 (0~1，越高信号越强) ──
    bull_strength = max(0, (bull_prob - 0.40) / 0.30)  # 0.40~0.70 映射到 0~1
    bear_strength = max(0, (bear_prob - 0.35) / 0.30)  # 0.35~0.65 映射到 0~1
    bull_strength = min(1.0, bull_strength)
    bear_strength = min(1.0, bear_strength)

    # ── 仓位建议 (基准仓位 50%) ──
    base_position = 50  # 基准仓位 50%

    if signal_code == "BULL":
        # 根据 Bull 概率强度加仓，最多到 70%
        position = base_position + int(bull_strength * 20)
        position_advice = f"建议仓位 {position}%（基准 50% + 多头信号加仓 {position - 50}%）"
        action = "可小幅加仓或维持多头持仓"
        risk_level = "🟡 中等"
    elif signal_code == "BEAR":
        # 根据 Bear 概率强度减仓，最少到 20%
        reduction = int(bear_strength * 30)
        position = base_position - reduction
        position_advice = f"建议仓位 {position}%（基准 50% - 空头信号减仓 {reduction}%）"
        action = "建议减仓或设置止损保护"
        risk_level = "🔴 偏高"
    elif signal_code == "NEUTRAL":
        position = base_position
        position_advice = f"建议仓位 {position}%（维持基准仓位）"
        action = "维持当前仓位，无需操作"
        risk_level = "🟢 较低"
    else:  # VOLATILE
        position = max(30, base_position - 15)
        position_advice = f"建议仓位 {position}%（基准 50% - 波动防御 15%）"
        action = "降低杠杆，设置止损止盈"
        risk_level = "🔴 高"

    # ── 风控规则 ──
    risk_notes = []
    if bear_prob > 0.55:
        risk_notes.append("⚠️ 大跌概率较高，务必设置止损")
    if bull_prob > 0.60 and bear_prob > 0.40:
        risk_notes.append("⚠️ 涨跌概率均较高，市场方向不明，控制仓位")
    if bull_prob < 0.35 and bear_prob < 0.35:
        risk_notes.append("ℹ️ 两个方向的信号均较弱，模型信心不足")

    # ── 模型局限性提醒 ──
    risk_notes.append("📊 模型 Kappa≈0.05，预测力有限，仅作辅助参考")

    return {
        "signal": signal,
        "signal_code": signal_code,
        "bull_prob": bull_prob,
        "bear_prob": bear_prob,
        "bull_strength": bull_strength,
        "bear_strength": bear_strength,
        "position_pct": position,
        "position_advice": position_advice,
        "action": action,
        "risk_level": risk_level,
        "risk_notes": risk_notes,
    }


def format_report(
    date_str: str,
    price: float,
    advice: dict,
    bull_prob: float,
    bear_prob: float,
    bull_meta: dict = None,
    bear_meta: dict = None,
) -> str:
    """格式化输出交易信号报告（含模型元信息）."""
    lines = []
    bull_meta = bull_meta or {}
    bear_meta = bear_meta or {}
    lines.append("=" * 60)
    lines.append(f"🔮 FcstLabPro 每日交易信号 (Bull={bull_meta.get('version','N/A')}, Bear={bear_meta.get('version','N/A')})")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"📅 信号日期: {date_str}")
    lines.append(f"💰 当前价格: ${price:,.2f}")
    lines.append(f"📊 预测窗口: 未来 14 天")
    lines.append("")

    # 模型信息
    lines.append(f"模型版本: Bull={bull_meta.get('version','N/A')}, Bear={bear_meta.get('version','N/A')}")
    lines.append(f"Kappa: Bull={bull_meta.get('kappa','N/A')}, Bear={bear_meta.get('kappa','N/A')}")
    lines.append(f"标签策略: {bull_meta.get('label_strategy','N/A')} / {bear_meta.get('label_strategy','N/A')}")
    lines.append(f"特征集: {', '.join(bull_meta.get('feature_set', []))}")
    lines.append("")

    # ── 概率仪表盘 ──
    lines.append("── 概率仪表盘 ──────────────────────────")
    bull_bar = "█" * int(bull_prob * 20) + "░" * (20 - int(bull_prob * 20))
    bear_bar = "█" * int(bear_prob * 20) + "░" * (20 - int(bear_prob * 20))
    lines.append(f"  🐂 大涨概率: [{bull_bar}] {bull_prob:.1%}")
    lines.append(f"  🐻 大跌概率: [{bear_bar}] {bear_prob:.1%}")
    lines.append("")

    # ── 综合信号 ──
    lines.append("── 综合信号 ────────────────────────────")
    lines.append(f"  信号: {advice['signal']}")
    lines.append(f"  风险: {advice['risk_level']}")
    lines.append("")

    # ── 交易建议 ──
    lines.append("── 交易建议 ────────────────────────────")
    lines.append(f"  操作: {advice['action']}")
    lines.append(f"  仓位: {advice['position_advice']}")
    lines.append("")

    # ── 仓位示意 ──
    pos = advice["position_pct"]
    pos_bar = "█" * (pos // 5) + "░" * ((100 - pos) // 5)
    lines.append(f"  仓位: [{pos_bar}] {pos}%")
    lines.append("")

    # ── 风控提醒 ──
    lines.append("── 风控提醒 ────────────────────────────")
    for note in advice["risk_notes"]:
        lines.append(f"  {note}")
    lines.append("")

    # ── 免责 ──
    lines.append("── 免责声明 ────────────────────────────")
    lines.append("  本信号基于历史技术面特征的统计模型，")
    lines.append(f"  当前模型 Kappa≈{bull_meta.get('kappa','N/A')} / {bear_meta.get('kappa','N/A')}，预测")
    lines.append("  力有限，请结合基本面、宏观环境、个人风")
    lines.append("  险承受能力综合判断。")
    lines.append("=" * 60)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="v9 每日交易信号")
    parser.add_argument("--download", action="store_true",
                        help="下载最新数据后再预测")
    parser.add_argument("--bull-dir", default=DEFAULT_BULL_DIR,
                        help="Bull 模型目录")
    parser.add_argument("--bear-dir", default=DEFAULT_BEAR_DIR,
                        help="Bear 模型目录")
    parser.add_argument("--bull-threshold", type=float, default=0.50,
                        help="Bull 判定阈值")
    parser.add_argument("--bear-threshold", type=float, default=0.50,
                        help="Bear 判定阈值")
    parser.add_argument("--save", action="store_true",
                        help="保存信号到 JSON 文件")
    args = parser.parse_args()

    try:
        # 1. 加载模型
        logger.info("📦 加载 Bull 模型: %s", args.bull_dir)
        bull_model, bull_config, bull_meta = load_model_and_features(args.bull_dir)
        logger.info("📦 加载 Bear 模型: %s", args.bear_dir)
        bear_model, bear_config, bear_meta = load_model_and_features(args.bear_dir)
        # 调试输出 bull_meta, bear_meta
        logger.info(f"[DEBUG] bull_meta: {bull_meta}")
        logger.info(f"[DEBUG] bear_meta: {bear_meta}")

        # 2. 计算特征 (两个模型用各自的特征集)
        logger.info("🔧 计算特征 (download=%s)...", args.download)
        bull_df = compute_latest_features(bull_config, download=args.download)
        bear_df = compute_latest_features(bear_config, download=args.download)

        bull_features = get_feature_columns(bull_df)
        bull_top_n = bull_config.get('features', {}).get('selection', {}).get('top_n')
        if bull_top_n:
            bull_features = bull_features[:bull_top_n]
        bear_features = get_feature_columns(bear_df)
        bear_top_n = bear_config.get('features', {}).get('selection', {}).get('top_n')
        if bear_top_n:
            bear_features = bear_features[:bear_top_n]

        logger.info("  Bull 特征数: %d, 数据行数: %d", len(bull_features), len(bull_df))
        logger.info("  Bear 特征数: %d, 数据行数: %d", len(bear_features), len(bear_df))

        X_bull = bull_df[bull_features].iloc[[-1]].values
        X_bear = bear_df[bear_features].iloc[[-1]].values

        # 3. 预测概率
        bull_proba = bull_model.predict_proba(X_bull)[0]  # [P(不涨), P(大涨)]
        bear_proba = bear_model.predict_proba(X_bear)[0]  # [P(不跌), P(大跌)]

        bull_prob = float(bull_proba[1])  # P(大涨)
        bear_prob = float(bear_proba[1])  # P(大跌)

        logger.info("📊 预测结果: Bull=%.3f, Bear=%.3f", bull_prob, bear_prob)

        # 4. 生成信号和建议
        advice = get_signal_and_advice(
            bull_prob, bear_prob,
            bull_threshold=args.bull_threshold,
            bear_threshold=args.bear_threshold,
        )

        # 5. 输出报告
        date_str = str(bull_df.index[-1].date())
        price = float(bull_df["close"].iloc[-1])

        # 风险提醒动态 Kappa
        kappa_bull = bull_meta.get("kappa", "N/A")
        kappa_bear = bear_meta.get("kappa", "N/A")
        kappa_str = f"Bull={kappa_bull}, Bear={kappa_bear}"
        # 修改 advice 生成前，动态插入 Kappa 风险提醒
        advice["risk_notes"] = [
            n if not n.startswith("📊 模型 Kappa") else f"📊 模型 Kappa≈{kappa_str}，预测力有限，仅作辅助参考"
            for n in advice["risk_notes"]
        ]

        report = format_report(date_str, price, advice, bull_prob, bear_prob, bull_meta, bear_meta)
        print(report)

        # 5.1 自动保存 Markdown 报告到 reports/signal_report_{date}.md
        reports_dir = PROJECT_ROOT / "reports"
        reports_dir.mkdir(exist_ok=True)
        md_path = reports_dir / f"signal_report_{date_str}.md"
        with open(md_path, "w") as f:
            f.write(report)
        logger.info("📝 信号报告已保存: %s", md_path)

        # 5.5 LLM 策略分析（可选，需配置 GEMINI_API_KEY）
        llm_analysis = None
        try:
            # 准备近 7 天 K 线数据
            recent = bull_df.tail(7)
            recent_klines = []
            for idx, row in recent.iterrows():
                prev_close = bull_df["close"].shift(1).loc[idx]
                change = ((row["close"] - prev_close) / prev_close * 100) if prev_close else 0
                recent_klines.append({
                    "date": str(idx.date()),
                    "close": float(row["close"]),
                    "change": float(change),
                    "volume": float(row["volume"]),
                })

            # 准备关键技术指标快照
            last_row = bull_df.iloc[-1]
            indicators = {}
            for col in ["rsi_14", "macd", "macd_hist", "bb_pctb_20", "atr_pct_14",
                         "sma_cross_50_200", "price_vs_sma_20", "price_vs_sma_200",
                         "vol_ratio_20", "return_7d", "return_14d", "volatility_20d"]:
                if col in last_row.index:
                    indicators[col] = float(last_row[col])

            signal_data = {
                "date": date_str,
                "price": price,
                "bull_prob": bull_prob,
                "bear_prob": bear_prob,
                "signal_display": advice["signal"],
                "position_pct": advice["position_pct"],
            }

            llm_analysis = generate_analysis(signal_data, recent_klines, indicators)
            if llm_analysis:
                print("\n📝 AI 策略解读:")
                print("-" * 50)
                print(llm_analysis)
                print("-" * 50)
        except Exception as e:
            logger.warning("⚠️ LLM 分析跳过: %s", e)

        # 6. 可选：保存 JSON
        if args.save:
            result = {
                "date": date_str,
                "price": price,
                "bull_prob": bull_prob,
                "bear_prob": bear_prob,
                "signal": advice["signal_code"],
                "signal_display": advice["signal"],
                "position_pct": advice["position_pct"],
                "action": advice["action"],
                "risk_level": advice["risk_level"],
                "risk_notes": advice["risk_notes"],
                "llm_analysis": llm_analysis,
                "model_version": {
                    "bull": bull_meta.get("version", "N/A"),
                    "bear": bear_meta.get("version", "N/A")
                },
                "kappa": {
                    "bull": bull_meta.get("kappa", "N/A"),
                    "bear": bear_meta.get("kappa", "N/A")
                },
                "label_strategy": {
                    "bull": bull_meta.get("label_strategy", "N/A"),
                    "bear": bear_meta.get("label_strategy", "N/A")
                },
                "feature_set": {
                    "bull": bull_meta.get("feature_set", []),
                    "bear": bear_meta.get("feature_set", [])
                },
                "prediction_window": "14 days",
                "data_source": "Binance BTCUSDT 1d",
                "generated_at": datetime.now().isoformat(),
            }
            out_dir = PROJECT_ROOT / "signals"
            out_dir.mkdir(exist_ok=True)
            out_path = out_dir / f"signal_{date_str}.json"
            with open(out_path, "w") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            logger.info("💾 信号已保存: %s", out_path)

    except Exception as e:
        logger.error("❌ 信号生成失败: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
