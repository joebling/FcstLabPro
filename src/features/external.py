"""外部数据特征集 — 基于真实外部数据源构建特征.

与 onchain.py / sentiment.py 中的代理指标不同，
本模块使用真实的外部数据（FGI、宏观因子、Funding Rate 等），
提供与价格行为低相关的独立信息维度。

使用方式:
  1. 先运行 `scripts/download_external_data.py` 下载外部数据
  2. 在特征配置中加入 "external" 特征集
  3. builder.py 会自动加载并合并
"""

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
