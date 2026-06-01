"""外部数据特征集 — 基于真实外部数据源构建特征.

与 onchain.py / sentiment.py 中的代理指标不同，
本模块使用真实的外部数据（FGI、宏观因子、Funding Rate 等），
提供与价格行为低相关的独立信息维度。

使用方式:
  1. 先运行 `scripts/download_external_data.py` 下载外部数据
  2. 在特征配置中加入 "external" 特征集
  3. builder.py 会自动加载并合并
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.features.registry import register_feature_set

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXTERNAL_DATA_DIR = PROJECT_ROOT / "data" / "external"


def _load_external_csv(filename: str) -> pd.DataFrame | None:
    """安全加载外部数据 CSV 文件."""
    path = EXTERNAL_DATA_DIR / filename
    if not path.exists():
        logger.warning(f"外部数据文件不存在: {path}，跳过")
        return None
    df = pd.read_csv(path, parse_dates=["date"], index_col="date")
    return df


def _load_onchain_csv(name: str) -> pd.DataFrame | None:
    """加载 BGeometrics 链上指标 CSV.

    Source: scripts/download_onchain_bgeo.py 从 charts.bgeometrics.com
    Schema: date,value
    Path: data/external/onchain/{name}.csv
    """
    path = EXTERNAL_DATA_DIR / "onchain" / f"{name}.csv"
    if not path.exists():
        logger.warning(f"链上数据不存在: {path}, 跳过")
        return None
    return pd.read_csv(path, parse_dates=["date"], index_col="date")


# Layer 0 数据治理 (phase2.5_feature_landscape_v0601.md §3):
# 链上指标 t 日的值通常是 t 日 UTC 结束后才能算出, 模型 t 日决策时不可用.
# 默认 availability_lag = 1 天 (即 t 日决策只能用 t-1 及之前的链上数据).
ONCHAIN_AVAILABILITY_LAG_DAYS = 1


def _load_onchain_series(
    name: str,
    target_index: pd.Index,
    availability_lag_days: int = ONCHAIN_AVAILABILITY_LAG_DAYS,
) -> pd.Series | None:
    """加载链上指标并对齐到主数据日期索引 (ffill + 防未来函数 shift).

    Args:
        name: 指标名 (对应 data/external/onchain/{name}.csv).
        target_index: 主数据 (BTC OHLCV) 的日期索引.
        availability_lag_days: 链上数据可用延迟天数. 默认 1 天,
            因为 t 日 UTC 结束后才能计算 t 日的链上聚合值,
            模型 t 日开盘决策时只能拿到 <= t-1 的数据 (Layer 0 防护).

    返回 None 则表示文件缺失, 调用方需处理.
    """
    data = _load_onchain_csv(name)
    if data is None or "value" not in data.columns:
        return None
    aligned = data["value"].reindex(target_index, method="ffill")
    if availability_lag_days > 0:
        aligned = aligned.shift(availability_lag_days)
    return aligned


@register_feature_set("external")
def build_external_features(df: pd.DataFrame) -> pd.DataFrame:
    """构建基于真实外部数据的特征.

    自动检测已下载的外部数据文件，有什么用什么。
    对缺失数据做前向填充（宏观数据周末无交易是正常的）。
    """
    df = df.copy()
    n_before = len(df.columns)

    # ============================
    # 1. 恐惧贪婪指数 (FGI)
    # ============================
    fgi = _load_external_csv("fear_greed_index.csv")
    if fgi is not None and "fgi_value" in fgi.columns:
        # 对齐到主数据的日期索引
        fgi_aligned = fgi["fgi_value"].reindex(df.index, method="ffill")
        df["ext_fgi"] = fgi_aligned

        # FGI 衍生特征
        df["ext_fgi_ma7"] = df["ext_fgi"].rolling(7).mean()
        df["ext_fgi_ma14"] = df["ext_fgi"].rolling(14).mean()
        df["ext_fgi_ma30"] = df["ext_fgi"].rolling(30).mean()
        df["ext_fgi_change_7d"] = df["ext_fgi"].pct_change(7)
        df["ext_fgi_change_14d"] = df["ext_fgi"].pct_change(14)
        df["ext_fgi_std_14"] = df["ext_fgi"].rolling(14).std()

        # 极端值标记（使用真实 FGI 分界线）
        df["ext_fgi_extreme_fear"] = (df["ext_fgi"] < 25).astype(int)
        df["ext_fgi_extreme_greed"] = (df["ext_fgi"] > 75).astype(int)

        # FGI 与价格的背离（FGI 降但价格涨 → 潜在顶部）
        price_ret_7 = df["close"].pct_change(7)
        fgi_ret_7 = df["ext_fgi"].pct_change(7)
        df["ext_fgi_price_divergence"] = fgi_ret_7 - price_ret_7

        logger.info(f"  ✅ FGI 特征: 11 个")

    # ============================
    # 2. 宏观因子
    # ============================
    macro = _load_external_csv("macro_factors.csv")
    if macro is not None:
        for col in macro.columns:
            # 获取因子名 (如 dxy_close → dxy)
            factor_name = col.replace("_close", "")

            # 对齐（宏观数据按工作日，需要前向填充到周末/加密市场交易日）
            aligned = macro[col].reindex(df.index, method="ffill")
            df[f"ext_{factor_name}"] = aligned

            # 收益率
            for w in [1, 5, 10, 20]:
                df[f"ext_{factor_name}_ret_{w}d"] = df[f"ext_{factor_name}"].pct_change(w)

            # 均线
            for w in [10, 20, 50]:
                ma = df[f"ext_{factor_name}"].rolling(w).mean()
                df[f"ext_{factor_name}_vs_ma{w}"] = (
                    (df[f"ext_{factor_name}"] - ma) / (ma.abs() + 1e-10)
                )

            # 波动率
            df[f"ext_{factor_name}_vol_20d"] = (
                df[f"ext_{factor_name}"].pct_change().rolling(20).std()
            )

        # 跨市场相关性（BTC vs 宏观因子的滚动相关）
        btc_ret = df["close"].pct_change()
        for factor_name_raw in macro.columns:
            factor_name = factor_name_raw.replace("_close", "")
            factor_col = f"ext_{factor_name}"
            if factor_col in df.columns:
                factor_ret = df[factor_col].pct_change()
                for w in [20, 60]:
                    df[f"ext_btc_{factor_name}_corr_{w}d"] = (
                        btc_ret.rolling(w).corr(factor_ret)
                    )

        n_macro_cols = sum(1 for c in df.columns if c.startswith("ext_") and
                          any(c.startswith(f"ext_{f.replace('_close', '')}") for f in macro.columns))
        logger.info(f"  ✅ 宏观因子特征: ~{n_macro_cols} 个")

    # ============================
    # 3. Funding Rate
    # ============================
    fr = _load_external_csv("funding_rate_BTCUSDT.csv")
    if fr is not None:
        for col in ["funding_rate_mean", "funding_rate_sum",
                     "funding_rate_max", "funding_rate_min"]:
            if col in fr.columns:
                aligned = fr[col].reindex(df.index, method="ffill")
                df[f"ext_{col}"] = aligned

        # Funding Rate 衍生特征
        if "ext_funding_rate_mean" in df.columns:
            fr_col = df["ext_funding_rate_mean"]
            for w in [7, 14, 30]:
                df[f"ext_fr_ma_{w}"] = fr_col.rolling(w).mean()
                df[f"ext_fr_std_{w}"] = fr_col.rolling(w).std()

            # 累积 funding（持续正 = 多头过度拥挤）
            df["ext_fr_cumsum_7"] = fr_col.rolling(7).sum()
            df["ext_fr_cumsum_14"] = fr_col.rolling(14).sum()
            df["ext_fr_cumsum_30"] = fr_col.rolling(30).sum()

            # 极端值标记
            fr_mean = fr_col.rolling(90).mean()
            fr_std = fr_col.rolling(90).std()
            df["ext_fr_zscore"] = (fr_col - fr_mean) / (fr_std + 1e-10)
            df["ext_fr_extreme_high"] = (df["ext_fr_zscore"] > 2).astype(int)
            df["ext_fr_extreme_low"] = (df["ext_fr_zscore"] < -2).astype(int)

        logger.info(f"  ✅ Funding Rate 特征: ~18 个")

    # ============================
    # 4. Long/Short Ratio
    # ============================
    ls = _load_external_csv("long_short_ratio_BTCUSDT.csv")
    if ls is not None:
        for col in ["ls_ratio", "long_account", "short_account"]:
            if col in ls.columns:
                aligned = ls[col].reindex(df.index, method="ffill")
                df[f"ext_{col}"] = aligned

        if "ext_ls_ratio" in df.columns:
            ls_col = df["ext_ls_ratio"]
            for w in [7, 14, 30]:
                df[f"ext_ls_ma_{w}"] = ls_col.rolling(w).mean()

            # 多空比变化
            for w in [1, 3, 7]:
                df[f"ext_ls_change_{w}d"] = ls_col.pct_change(w)

            # 多空比极端
            ls_mean = ls_col.rolling(60).mean()
            ls_std = ls_col.rolling(60).std()
            df["ext_ls_zscore"] = (ls_col - ls_mean) / (ls_std + 1e-10)

        logger.info(f"  ✅ Long/Short Ratio 特征: ~12 个")

    n_new = len(df.columns) - n_before
    logger.info(f"外部数据特征集构建完成: 新增 {n_new} 个特征")

    return df


# ============================================================
# 消融实验用: 拆分的子特征集
# ============================================================

@register_feature_set("external_fgi")
def build_external_fgi_features(df: pd.DataFrame) -> pd.DataFrame:
    """仅构建 FGI 特征 (用于消融实验)."""
    df = df.copy()
    fgi = _load_external_csv("fear_greed_index.csv")
    if fgi is not None and "fgi_value" in fgi.columns:
        fgi_aligned = fgi["fgi_value"].reindex(df.index, method="ffill")
        df["ext_fgi"] = fgi_aligned
        df["ext_fgi_ma7"] = df["ext_fgi"].rolling(7).mean()
        df["ext_fgi_ma14"] = df["ext_fgi"].rolling(14).mean()
        df["ext_fgi_ma30"] = df["ext_fgi"].rolling(30).mean()
        df["ext_fgi_change_7d"] = df["ext_fgi"].pct_change(7)
        df["ext_fgi_change_14d"] = df["ext_fgi"].pct_change(14)
        df["ext_fgi_std_14"] = df["ext_fgi"].rolling(14).std()
        df["ext_fgi_extreme_fear"] = (df["ext_fgi"] < 25).astype(int)
        df["ext_fgi_extreme_greed"] = (df["ext_fgi"] > 75).astype(int)
        price_ret_7 = df["close"].pct_change(7)
        fgi_ret_7 = df["ext_fgi"].pct_change(7)
        df["ext_fgi_price_divergence"] = fgi_ret_7 - price_ret_7
        logger.info("  ✅ FGI 子特征集: 11 个")
    else:
        logger.warning("  ⚠️ FGI 数据不可用")
    return df


@register_feature_set("external_fgi_enhanced")
def build_external_fgi_enhanced_features(df: pd.DataFrame) -> pd.DataFrame:
    """增强版 FGI 特征 - 添加更多衍生特征."""
    df = df.copy()
    fgi = _load_external_csv("fear_greed_index.csv")
    if fgi is not None and "fgi_value" in fgi.columns:
        fgi_aligned = fgi["fgi_value"].reindex(df.index, method="ffill")
        df["ext_fgi"] = fgi_aligned

        # 基础统计特征
        for w in [3, 7, 14, 21, 30]:
            df[f"ext_fgi_ma{w}"] = df["ext_fgi"].rolling(w).mean()
            df[f"ext_fgi_std_{w}"] = df["ext_fgi"].rolling(w).std()

        # 动量特征
        for w in [1, 3, 5, 7, 14, 21]:
            df[f"ext_fgi_change_{w}d"] = df["ext_fgi"].pct_change(w)

        # FGI 位置特征 (在历史分布中的位置)
        for w in [30, 60, 90]:
            fgi_roll = df["ext_fgi"].rolling(w)
            df[f"ext_fgi_pct_rank_{w}"] = df["ext_fgi"].rank(pct=True) - 0.5

        # 极端值特征
        df["ext_fgi_extreme_fear"] = (df["ext_fgi"] < 25).astype(int)
        df["ext_fgi_extreme_greed"] = (df["ext_fgi"] > 75).astype(int)
        df["ext_fgi_fear"] = (df["ext_fgi"] < 35).astype(int)
        df["ext_fgi_greed"] = (df["ext_fgi"] > 65).astype(int)

        # FGI 与价格背离
        for w in [7, 14]:
            price_ret = df["close"].pct_change(w)
            fgi_ret = df["ext_fgi"].pct_change(w)
            df[f"ext_fgi_price_div_{w}d"] = fgi_ret - price_ret

        # FGI 动量方向变化 (加速度)
        df["ext_fgi_momentum"] = df["ext_fgi"].diff(3)
        df["ext_fgi_momentum_accel"] = df["ext_fgi_momentum"].diff(3)

        # FGI 与均线偏离
        for w in [14, 30]:
            ma = df["ext_fgi"].rolling(w).mean()
            df[f"ext_fgi_vs_ma{w}"] = df["ext_fgi"] - ma

        logger.info("  ✅ FGI 增强特征集: 40+ 个")
    else:
        logger.warning("  ⚠️ FGI 数据不可用")
    return df


@register_feature_set("external_macro")
def build_external_macro_features(df: pd.DataFrame) -> pd.DataFrame:
    """仅构建宏观因子特征 (用于消融实验)."""
    df = df.copy()
    macro = _load_external_csv("macro_factors.csv")
    if macro is not None:
        btc_ret = df["close"].pct_change()
        for col in macro.columns:
            factor_name = col.replace("_close", "")
            aligned = macro[col].reindex(df.index, method="ffill")
            df[f"ext_{factor_name}"] = aligned
            for w in [1, 5, 10, 20]:
                df[f"ext_{factor_name}_ret_{w}d"] = df[f"ext_{factor_name}"].pct_change(w)
            for w in [10, 20, 50]:
                ma = df[f"ext_{factor_name}"].rolling(w).mean()
                df[f"ext_{factor_name}_vs_ma{w}"] = (
                    (df[f"ext_{factor_name}"] - ma) / (ma.abs() + 1e-10)
                )
            df[f"ext_{factor_name}_vol_20d"] = (
                df[f"ext_{factor_name}"].pct_change().rolling(20).std()
            )
            factor_ret = df[f"ext_{factor_name}"].pct_change()
            for w in [20, 60]:
                df[f"ext_btc_{factor_name}_corr_{w}d"] = (
                    btc_ret.rolling(w).corr(factor_ret)
                )
        logger.info("  ✅ 宏观因子子特征集构建完成")
    else:
        logger.warning("  ⚠️ 宏观因子数据不可用")
    return df


@register_feature_set("external_fr")
def build_external_fr_features(df: pd.DataFrame) -> pd.DataFrame:
    """仅构建 Funding Rate 特征 (用于消融实验)."""
    df = df.copy()
    fr = _load_external_csv("funding_rate_BTCUSDT.csv")
    if fr is not None:
        for col in ["funding_rate_mean", "funding_rate_sum",
                     "funding_rate_max", "funding_rate_min"]:
            if col in fr.columns:
                aligned = fr[col].reindex(df.index, method="ffill")
                df[f"ext_{col}"] = aligned
        if "ext_funding_rate_mean" in df.columns:
            fr_col = df["ext_funding_rate_mean"]
            for w in [7, 14, 30]:
                df[f"ext_fr_ma_{w}"] = fr_col.rolling(w).mean()
                df[f"ext_fr_std_{w}"] = fr_col.rolling(w).std()
            df["ext_fr_cumsum_7"] = fr_col.rolling(7).sum()
            df["ext_fr_cumsum_14"] = fr_col.rolling(14).sum()
            df["ext_fr_cumsum_30"] = fr_col.rolling(30).sum()
            fr_mean = fr_col.rolling(90).mean()
            fr_std = fr_col.rolling(90).std()
            df["ext_fr_zscore"] = (fr_col - fr_mean) / (fr_std + 1e-10)
            df["ext_fr_extreme_high"] = (df["ext_fr_zscore"] > 2).astype(int)
            df["ext_fr_extreme_low"] = (df["ext_fr_zscore"] < -2).astype(int)
        logger.info("  ✅ Funding Rate 子特征集构建完成")
    else:
        logger.warning("  ⚠️ Funding Rate 数据不可用")
    return df


@register_feature_set("external_mvrv")
def build_external_mvrv_features(df: pd.DataFrame) -> pd.DataFrame:
    """仅构建 MVRV 链上估值特征 (用于消融实验).

    MVRV = Market Value / Realized Value, 链上慢变量, 与价格低相关,
    能识别整个减半周期。数据源: scripts/download_mvrv.py (CoinMetrics)。
    共 12 个特征, 见 docs/plans/feature_engineering_roadmap.md §2.3。
    """
    df = df.copy()
    mvrv_data = _load_external_csv("mvrv_btc.csv")
    if mvrv_data is not None and "mvrv" in mvrv_data.columns:
        # 对齐到主数据索引, ffill 应对链上数据 1-2 天延迟
        mvrv = mvrv_data["mvrv"].reindex(df.index, method="ffill")

        df["ext_mvrv"] = mvrv                                    # 核心
        df["ext_mvrv_ma_30"] = mvrv.rolling(30).mean()          # 短期平滑
        df["ext_mvrv_ma_90"] = mvrv.rolling(90).mean()          # 周期视角
        df["ext_mvrv_change_7"] = mvrv.pct_change(7)            # 周环比
        df["ext_mvrv_change_30"] = mvrv.pct_change(30)          # 月环比

        # 1 年滚动 Z-score (即 MVRV-Z Score)
        ma365 = mvrv.rolling(365).mean()
        std365 = mvrv.rolling(365).std()
        df["ext_mvrv_zscore_365"] = (mvrv - ma365) / (std365 + 1e-10)

        # 2 年历史分布百分位
        df["ext_mvrv_pct_rank_730"] = mvrv.rolling(730).apply(
            lambda x: (x.iloc[-1] >= x).mean(), raw=False
        )

        # 阈值特征 (Messari 顶部 / 资金成本线 / 警戒区 / 机会区)
        df["ext_mvrv_extreme_top"] = (mvrv >= 3.0).astype(int)
        df["ext_mvrv_extreme_bottom"] = (mvrv <= 1.0).astype(int)
        df["ext_mvrv_in_top_zone"] = (mvrv >= 2.5).astype(int)
        df["ext_mvrv_in_bottom_zone"] = (mvrv <= 1.2).astype(int)

        # 30 日线性斜率 (趋势加速度)
        df["ext_mvrv_slope_30"] = mvrv.rolling(30).apply(
            lambda x: np.polyfit(range(len(x)), x, 1)[0], raw=True
        )

        logger.info("  ✅ MVRV 子特征集构建完成 (12 特征)")
    else:
        logger.warning("  ⚠️ MVRV 数据不可用 (运行 scripts/download_mvrv.py 后回传 CSV)")
    return df


# ============================================================
# BGeometrics LTH/STH 链上指标 (Phase 2.5)
# ------------------------------------------------------------
# 数据源: charts.bgeometrics.com/files/{indicator}.json
# 落地: data/external/onchain/{indicator}.csv
# 下载: scripts/download_onchain_bgeo.py
# 参考: docs/plans/onchain_lth_sth_feature_plan.md
# ============================================================

# 6 个核心 LTH/STH 指标 (持币 ≥/< 155 天的行为分化)
LTH_STH_INDICATORS = [
    "lth_mvrv", "sth_mvrv",     # 长/短期持有者 MVRV
    "lth_nupl", "sth_nupl",     # LTH/STH NUPL (净未实现盈亏)
    "lth_sopr", "sth_sopr",     # LTH/STH SOPR (实际抛压)
]


def _add_indicator_features(
    df: pd.DataFrame, name: str, series: pd.Series,
) -> int:
    """为单个指标添加 6 个标准衍生特征 (raw + ma_7/30 + change_7/30 + slope_30).

    返回新增列数 (固定 6).
    """
    df[f"ext_{name}"] = series
    df[f"ext_{name}_ma_7"] = series.rolling(7).mean()
    df[f"ext_{name}_ma_30"] = series.rolling(30).mean()
    df[f"ext_{name}_change_7"] = series.pct_change(7)
    df[f"ext_{name}_change_30"] = series.pct_change(30)
    df[f"ext_{name}_slope_30"] = series.rolling(30).apply(
        lambda x: np.polyfit(range(len(x)), x, 1)[0], raw=True
    )
    return 6


@register_feature_set("external_lth_sth_core")
def build_lth_sth_core_features(df: pd.DataFrame) -> pd.DataFrame:
    """6 个 LTH/STH 链上原生指标 × 6 个衍生 = 36 特征.

    包含: lth/sth × mvrv/nupl/sopr.
    每个指标的衍生: raw, ma_7, ma_30, change_7, change_30, slope_30.

    用途: E18a 实验. 详见 docs/plans/experiment_matrix_v0601.md §5.1.
    """
    df = df.copy()
    n_added = 0
    n_missing = 0

    for name in LTH_STH_INDICATORS:
        s = _load_onchain_series(name, df.index)
        if s is None:
            n_missing += 1
            continue
        n_added += _add_indicator_features(df, name, s)

    if n_added == 0:
        logger.warning(
            "  ⚠️ LTH/STH 链上数据全部缺失, 请运行: "
            "python scripts/download_onchain_bgeo.py --core-only"
        )
    else:
        logger.info(
            f"  ✅ LTH/STH core 特征: {n_added} 个 "
            f"({len(LTH_STH_INDICATORS) - n_missing}/{len(LTH_STH_INDICATORS)} 指标可用)"
        )
    return df


@register_feature_set("external_lth_sth_interactions")
def build_lth_sth_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """LTH vs STH 行为分化交互特征 (8 个).

    捕捉 "派发期顶部" / "全员恐慌底" 等典型周期信号.
    详见 onchain_lth_sth_feature_plan.md §3.3.
    """
    df = df.copy()
    # 一次性加载 6 个指标到缓存 (避免重复 IO)
    cache: dict[str, pd.Series] = {}
    for name in LTH_STH_INDICATORS:
        s = _load_onchain_series(name, df.index)
        if s is not None:
            cache[name] = s

    n_added = 0
    eps = 1e-6  # 防除零

    # MVRV 维度: 派发期 / 比率
    if "lth_mvrv" in cache and "sth_mvrv" in cache:
        df["ext_mvrv_lth_sth_diff"] = cache["lth_mvrv"] - cache["sth_mvrv"]
        df["ext_mvrv_lth_sth_ratio"] = cache["lth_mvrv"] / (cache["sth_mvrv"] + eps)
        n_added += 2

    # NUPL 维度: 情绪分化
    if "lth_nupl" in cache and "sth_nupl" in cache:
        df["ext_nupl_lth_sth_diff"] = cache["lth_nupl"] - cache["sth_nupl"]
        df["ext_nupl_lth_sth_ratio"] = cache["lth_nupl"] / (cache["sth_nupl"].abs() + eps)
        n_added += 2

    # SOPR 维度: 抛压分化
    if "lth_sopr" in cache and "sth_sopr" in cache:
        df["ext_sopr_lth_sth_diff"] = cache["lth_sopr"] - cache["sth_sopr"]
        n_added += 1

    # 周期信号 (阈值特征)
    if "lth_sopr" in cache:
        df["ext_lth_capitulation"] = (cache["lth_sopr"] < 1.0).astype(int)
        n_added += 1
    if "sth_sopr" in cache:
        df["ext_sth_panic"] = (cache["sth_sopr"] < 1.0).astype(int)
        n_added += 1
    if "lth_nupl" in cache:
        df["ext_lth_euphoria"] = (cache["lth_nupl"] > 0.75).astype(int)
        n_added += 1

    if n_added == 0:
        logger.warning(
            "  ⚠️ LTH/STH 交互特征 0 个 (数据缺失), 请运行: "
            "python scripts/download_onchain_bgeo.py --core-only"
        )
    else:
        logger.info(f"  ✅ LTH/STH interactions 特征: {n_added} 个")
    return df


# ============================================================
# Phase 2.5 Wave 2: Short-Horizon 派生 + E19-* feature sets
# ============================================================
#
# 设计依据 (phase2.5_feature_landscape_v0601.md §4 #6 慢变量纪律):
#   - raw level 禁止直接作为特征 (任何 >30 天周期指标都必须做转换)
#   - 必须的转换: zscore_30, zscore_90, slope_7, slope_30, momentum_7
#
# 依据 (phase2.5_feature_landscape_v0601.md §3 数据治理铁律):
#   - _load_onchain_series 已自动 shift(1) (Layer 0 防护)
#   - 不允许使用 *_btc_price.json (是 BTC 价格副轴)
# ============================================================


def _add_short_horizon_features(
    df: pd.DataFrame, name: str, series: pd.Series,
) -> int:
    """为单个慢变量指标添加 5 个 short-horizon 派生特征.

    遵守 phase2.5 §4 #6: 不含 raw, 全部 short-horizon 转换.

    生成的 5 个特征:
      - zscore_30: 30 天滚动 z-score
      - zscore_90: 90 天滚动 z-score
      - slope_7:   7 天线性回归斜率
      - slope_30:  30 天线性回归斜率
      - momentum_7: 7 天动量 (pct_change)

    返回新增列数 (固定 5).
    """
    def _zscore(s: pd.Series, w: int) -> pd.Series:
        mean = s.rolling(w).mean()
        std = s.rolling(w).std()
        return (s - mean) / (std + 1e-12)

    def _slope(s: pd.Series, w: int) -> pd.Series:
        return s.rolling(w).apply(
            lambda x: np.polyfit(range(len(x)), x, 1)[0], raw=True
        )

    df[f"ext_{name}_zscore_30"] = _zscore(series, 30)
    df[f"ext_{name}_zscore_90"] = _zscore(series, 90)
    df[f"ext_{name}_slope_7"] = _slope(series, 7)
    df[f"ext_{name}_slope_30"] = _slope(series, 30)
    df[f"ext_{name}_momentum_7"] = series.pct_change(7)
    return 5


@register_feature_set("external_puell")
def build_puell_features(df: pd.DataFrame) -> pd.DataFrame:
    """E19-PUELL: Puell Multiple (Charles Edwards) 周期 indicator.

    单一长历史指标 (2012-2025, 14 年, L1: cov 99.5%, stale 2d).
    经典 BTC 周期顶/底信号 (>4 = 顶部预警, <0.5 = 底部机会).

    生成 5 个 short-horizon 特征 (§4 #6, 不含 raw):
      ext_puell_zscore_30, _zscore_90, _slope_7, _slope_30, _momentum_7

    用途: E19-PUELL 实验 (优先级 1, Phase 2.5 Wave 2 第一炮).
    详见 docs/plans/phase2.5_feature_landscape_v0601.md §5.1.
    """
    df = df.copy()
    s = _load_onchain_series("puell_multiple_data", df.index)
    if s is None:
        logger.warning(
            "  ⚠️ puell_multiple_data.csv 缺失, 请先运行: "
            "python scripts/download_onchain_bgeo.py --indicators puell_multiple_data"
        )
        return df

    n_added = _add_short_horizon_features(df, "puell", s)
    logger.info(f"  ✅ E19-PUELL 特征: {n_added} 个 (puell_multiple_data, 2012-2025)")
    return df
