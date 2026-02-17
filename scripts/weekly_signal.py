#!/usr/bin/env python3
# Fix: 2026-02-17 - Bear model download parameter
# Fix: 2026-02-17 - Auto-download if file not found
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

# ── 限制线程数（必须在所有 import 之前设置） ──
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import argparse
import gc
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
import psutil
import torch
torch.set_num_threads(1)

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

# ── 内存监控函数 ──
def log_memory(prefix: str = ""):
    """打印当前内存使用情况 (MB)"""
    try:
        process = psutil.Process()
        mem_info = process.memory_info()
        rss_mb = mem_info.rss / 1024 / 1024
        logger.info(f"📊 {prefix} 内存: {rss_mb:.1f} MB")
    except Exception:
        pass  # 非关键功能，跳过

# ── 限制 PyTorch 线程数（减少内存占用） ──
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

# ── 默认模型路径 (v27: Orion-BiX n_estimators=16) ──
DEFAULT_BULL_DIR = "experiments/weekly/weekly_bull_v27_orion_final"
DEFAULT_BEAR_DIR = "experiments/weekly/weekly_bear_v13_T28_fgi_20260215_134804_ff4ad7"


# ── 进程级隔离函数 ──
def run_bull_with_features(model_dir: str, download: bool, temp_dir: str):
    """计算 Bull 特征 + 推理（进程A）."""
    import pickle
    from pathlib import Path

    logger.info("📦 [进程A] 加载 Bull 模型 + 计算特征 + 推理...")
    model, config, meta = load_model_and_features(model_dir)
    log_memory("加载 Bull 模型后")

    # 计算特征
    logger.info("🔧 计算 Bull 特征...")
    df = compute_latest_features(config, download=download)
    features = get_feature_columns(df)
    top_n = config.get('features', {}).get('selection', {}).get('top_n')
    if top_n:
        features = features[:top_n]

    logger.info(f"  Bull 特征数: {len(features)}, 数据行数: {len(df)}")
    X = df[features].iloc[[-1]].values.astype(np.float32)

    # 保存需要的信息后立即清理 DataFrame
    result_info = {
        'date': str(df.index[-1].date()),
        'price': float(df["close"].iloc[-1])
    }
    del df
    gc.collect()
    log_memory("清理 DataFrame 后")

    # 推理
    proba = model.predict_proba(X)[0]
    prob = float(proba[1])
    logger.info(f"📊 Bull 概率: {prob}")

    # 清理模型和特征矩阵
    del model, X
    gc.collect()
    log_memory("清理模型后")

    # 保存结果
    result = {
        'bull_prob': prob,
        'date': result_info['date'],
        'price': result_info['price']
    }
    output_file = Path(temp_dir) / "bull_result.pkl"
    with open(output_file, 'wb') as f:
        pickle.dump(result, f)

    logger.info(f"✅ [进程A] Bull 完成: {output_file}")
    log_memory("Bull 进程结束")
    return result


def run_bear_with_features(model_dir: str, download: bool, temp_dir: str):
    """计算 Bear 特征 + 推理（进程B）."""
    import pickle
    from pathlib import Path

    logger.info("📦 [进程B] 加载 Bear 模型 + 计算特征 + 推理...")
    model, config, meta = load_model_and_features(model_dir)
    log_memory("加载 Bear 模型后")

    # 计算特征
    logger.info("🔧 计算 Bear 特征...")
    df = compute_latest_features(config, download=True)
    features = get_feature_columns(df)
    top_n = config.get('features', {}).get('selection', {}).get('top_n')
    if top_n:
        features = features[:top_n]

    logger.info(f"  Bear 特征数: {len(features)}, 数据行数: {len(df)}")
    X = df[features].iloc[[-1]].values.astype(np.float32)

    # 清理 DataFrame
    del df
    gc.collect()
    log_memory("清理 DataFrame 后")

    # 推理
    proba = model.predict_proba(X)[0]
    prob = float(proba[1])
    logger.info(f"📊 Bear 概率: {prob}")

    # 清理模型和特征矩阵
    del model, X
    gc.collect()
    log_memory("清理模型后")

    # 保存结果
    result = {'bear_prob': prob}
    output_file = Path(temp_dir) / "bear_result.pkl"
    with open(output_file, 'wb') as f:
        pickle.dump(result, f)

    logger.info(f"✅ [进程B] Bear 完成: {output_file}")
    log_memory("Bear 进程结束")
    return result


def run_bear_infer(model_dir: str, temp_dir: str):
    """仅加载 Bear 模型并推理（进程C）."""
    import pickle
    from pathlib import Path

    logger.info("📦 [进程C] 加载 Bear 模型...")
    model, config, meta = load_model_and_features(model_dir)
    log_memory("加载 Bear 模型后")

    # 读取特征文件
    feature_file = Path(temp_dir) / "latest_features.pkl"
    with open(feature_file, 'rb') as f:
        data = pickle.load(f)

    X = data['X']
    logger.info(f"  Bear 特征数: {X.shape[1]}")

    # 推理
    proba = model.predict_proba(X)[0]
    prob = float(proba[1])
    logger.info(f"📊 Bear 概率: {prob}")

    # 保存结果
    result = {'bear_prob': prob}
    output_file = Path(temp_dir) / "bear_result.pkl"
    with open(output_file, 'wb') as f:
        pickle.dump(result, f)

    logger.info(f"✅ [进程C] Bear 推理完成")
    log_memory("Bear 推理完成")
    return result

# 保留旧函数名作为别名（兼容）
run_compute_features = run_bull_with_features
run_bull_infer = run_bull_with_features
run_bear_infer = run_bear_with_features


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
    """计算最新一天的特征（含数据裁剪以减少内存占用）."""
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
        try:
            df = load_csv(data_path)
        except FileNotFoundError:
            from src.data.downloader import download_binance_klines
            from pathlib import Path
            print("⚠️  数据文件不存在，自动下载...")
            df = download_binance_klines(
                symbol=data_cfg.get("symbol", "BTCUSDT"),
                interval=data_cfg.get("interval", "1d"),
                start="2020-01-01",
            )
            Path(data_path).parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(data_path)
            print(f"✅ 数据已保存到: {data_path}")

    # 更激进的数据裁剪：只保留最近 800 条记录
    max_rows = 800
    if len(df) > max_rows:
        logger.info(f"📐 数据裁剪: 从 {len(df)} 行减少到最近 {max_rows} 行")
        df = df.tail(max_rows).copy()

    feat_cfg = config["features"]
    df = build_features(df, feature_sets=feat_cfg["sets"])
    
    # 再次裁剪：特征计算后只保留最后 600 行
    if len(df) > 600:
        df = df.tail(600).copy()
    
    return df


def get_signal_and_advice(
    bull_prob: float,
    bear_prob: float,
    bull_threshold: float = 0.50,
    bear_threshold: float = 0.50,
    # 双模校验参数
    gbdt_bull_prob: float = None,
    gbdt_threshold: float = 0.40,
    dual_mode: bool = False,
) -> dict:
    """根据概率输出综合信号和交易建议.

    Parameters
    ----------
    bull_prob : Bull 模型 (Orion-BiX) 输出的 P(大涨) 概率
    bear_prob : Bear 模型 (GBDT) 输出的 P(大跌) 概率
    bull_threshold : Bull 判定阈值
    bear_threshold : Bear 判定阈值
    gbdt_bull_prob : GBDT Bull 模型概率 (双模校验用)
    gbdt_threshold : GBDT Bull 概率阈值 (双模校验用)
    dual_mode : 是否启用双模校验

    Returns
    -------
    dict : 包含 signal, position, advice, risk_level 等
    """
    # ── 双模校验逻辑 ──
    # "Orion 进攻，GBDT 防守"
    # Bull 信号: Orion-BiX 给出 Bull 信号 + GBDT 概率 > gbdt_threshold
    # Bear 信号: GBDT Bear 触发时无条件覆盖 Bull

    if dual_mode and gbdt_bull_prob is not None:
        # Orion-BiX Bull 信号需要 GBDT 确认
        orion_bull_on = bull_prob >= bull_threshold
        gbdt_confirm = gbdt_bull_prob >= gbdt_threshold

        bull_on = orion_bull_on and gbdt_confirm
        bear_on = bear_prob >= bear_threshold

        # Bear 无条件覆盖 Bull
        if bear_on:
            bull_on = False
    else:
        bull_on = bull_prob >= bull_threshold
        bear_on = bear_prob >= bear_threshold
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
                        help="Bull 模型目录 (Orion-BiX)")
    parser.add_argument("--bear-dir", default=DEFAULT_BEAR_DIR,
                        help="Bear 模型目录 (GBDT)")
    parser.add_argument("--gbdt-bull-dir",
                        help="GBDT Bull 模型目录 (双模校验用)")
    parser.add_argument("--bull-threshold", type=float, default=0.50,
                        help="Bull 判定阈值")
    parser.add_argument("--bear-threshold", type=float, default=0.50,
                        help="Bear 判定阈值")
    parser.add_argument("--gbdt-threshold", type=float, default=0.40,
                        help="GBDT Bull 确认阈值 (双模校验用)")
    parser.add_argument("--dual-mode", action="store_true",
                        help="启用双模校验: Orion 进攻 + GBDT 防守")
    parser.add_argument("--save", action="store_true",
                        help="保存信号到 JSON 文件")
    # 进程级隔离模式
    parser.add_argument("--mode", default="full",
                        choices=["full", "compute-features", "bull-infer", "bear-infer"],
                        help="运行模式: full=完整流程, compute-features=仅计算特征, bull-infer=仅Bull推理, bear-infer=仅Bear推理")
    parser.add_argument("--temp-dir", default="/tmp",
                        help="临时文件目录")
    args = parser.parse_args()

    # ── 进程级隔离模式处理 ──
    if args.mode == "bull-infer":
        # 进程A: Bull 特征计算 + 推理（完成后进程退出，释放内存）
        run_bull_with_features(args.bull_dir, args.download, args.temp_dir)
        return

    if args.mode == "bear-infer":
        # 进程B: Bear 特征计算 + 推理（完成后进程退出，释放内存）
        run_bear_with_features(args.bear_dir, args.download, args.temp_dir)
        return

    try:
        log_memory("初始")

        # ==================== 阶段性处理: Bull 模型 ====================
        logger.info("📦 加载 Bull 模型 (Orion-BiX): %s", args.bull_dir)
        bull_model, bull_config, bull_meta = load_model_and_features(args.bull_dir)
        log_memory("加载 Bull 模型后")

        logger.info(f"[DEBUG] bull_meta: {bull_meta}")

        # 计算 Bull 特征
        logger.info("🔧 计算 Bull 特征 (download=%s)...", args.download)
        bull_df = compute_latest_features(bull_config, download=args.download)
        log_memory("计算 Bull 特征后")

        bull_features = get_feature_columns(bull_df)
        bull_top_n = bull_config.get('features', {}).get('selection', {}).get('top_n')
        if bull_top_n:
            bull_features = bull_features[:bull_top_n]
        logger.info("  Bull 特征数: %d, 数据行数: %d", len(bull_features), len(bull_df))

        # 推理 - 只提取最后一行，转换为 float32
        X_bull = bull_df[bull_features].iloc[[-1]].values.astype(np.float32)
        bull_proba = bull_model.predict_proba(X_bull)[0]
        bull_prob = float(bull_proba[1])  # P(大涨) - Orion-BiX
        logger.info("📊 Bull 概率: %.3f", bull_prob)

        # 保存最后日期和价格（删除 bull_df 后仍需使用）
        last_date = str(bull_df.index[-1].date())
        last_price = float(bull_df["close"].iloc[-1])

        # 清理 Bull 模型（保留 bull_df 供后续 LLM 分析使用）
        del bull_model, X_bull
        gc.collect()
        log_memory("清理 Bull 模型后")

        # ==================== 阶段性处理: Bear 模型 ====================
        logger.info("📦 加载 Bear 模型 (GBDT): %s", args.bear_dir)
        bear_model, bear_config, bear_meta = load_model_and_features(args.bear_dir)
        log_memory("加载 Bear 模型后")

        logger.info(f"[DEBUG] bear_meta: {bear_meta}")

        # 计算 Bear 特征
        logger.info("🔧 计算 Bear 特征 (download=%s)...", args.download)
        bear_df = compute_latest_features(bear_config, download=args.download)
        log_memory("计算 Bear 特征后")

        bear_features = get_feature_columns(bear_df)
        bear_top_n = bear_config.get('features', {}).get('selection', {}).get('top_n')
        if bear_top_n:
            bear_features = bear_features[:bear_top_n]
        logger.info("  Bear 特征数: %d, 数据行数: %d", len(bear_features), len(bear_df))

        # 推理 - 只提取最后一行，转换为 float32
        X_bear = bear_df[bear_features].iloc[[-1]].values.astype(np.float32)
        bear_proba = bear_model.predict_proba(X_bear)[0]
        bear_prob = float(bear_proba[1])  # P(大跌) - GBDT

        # 清理 Bear 模型（保留 bear_df 供后续使用）
        del bear_model, X_bear
        gc.collect()
        log_memory("清理 Bear 模型后")

        # ==================== 双模校验 (如启用) ====================
        # 1.1 双模校验: 加载 GBDT Bull 模型
        gbdt_bull_model = None
        gbdt_bull_meta = None
        gbdt_bull_prob = None
        if args.dual_mode:
            gbdt_bull_dir = args.gbdt_bull_dir or "experiments/weekly/weekly_bull_v15_regime_20260215_142329_b42efc"
            logger.info("📦 加载 GBDT Bull 模型 (双模校验): %s", gbdt_bull_dir)
            gbdt_bull_model, gbdt_bull_config, gbdt_bull_meta = load_model_and_features(gbdt_bull_dir)
            log_memory("加载 GBDT Bull 模型后")

            # 重新加载 Bull 特征数据用于 GBDT 预测
            bull_df = compute_latest_features(bull_config, download=False)
            gbdt_bull_features = get_feature_columns(bull_df)
            gbdt_top_n = gbdt_bull_config.get('features', {}).get('selection', {}).get('top_n')
            if gbdt_top_n:
                gbdt_bull_features = gbdt_bull_features[:gbdt_top_n]

            X_gbdt_bull = bull_df[gbdt_bull_features].iloc[[-1]].values.astype(np.float32)
            gbdt_bull_proba = gbdt_bull_model.predict_proba(X_gbdt_bull)[0]
            gbdt_bull_prob = float(gbdt_bull_proba[1])
            logger.info("📊 GBDT Bull 概率 (双模校验): %.3f", gbdt_bull_prob)

            del gbdt_bull_model, bull_df, X_gbdt_bull
            gc.collect()

        logger.info("📊 预测结果: Bull=%.3f, Bear=%.3f", bull_prob, bear_prob)

        # 4. 生成信号和建议
        advice = get_signal_and_advice(
            bull_prob, bear_prob,
            bull_threshold=args.bull_threshold,
            bear_threshold=args.bear_threshold,
            gbdt_bull_prob=gbdt_bull_prob,
            gbdt_threshold=args.gbdt_threshold,
            dual_mode=args.dual_mode,
        )

        # 5. 输出报告
        date_str = last_date
        price = last_price

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

        # 最终清理 DataFrame
        del bull_df, bear_df
        gc.collect()

    except Exception as e:
        logger.error("❌ 信号生成失败: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
