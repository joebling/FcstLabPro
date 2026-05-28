#!/usr/bin/env python3
"""导出特征字典 CSV — 含分类 / 加工逻辑 / E1+E8 重要性.

生成的 CSV 用于:
  1. Review 当前生产模型使用了哪些特征
  2. 对比 E1 vs E8 的特征偏好差异
  3. 找出"两个模型都不用"的低价值特征 → 候选移除

Usage:
    python scripts/export_feature_dictionary.py
    # 输出: docs/specs/feature_dictionary.csv
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── 数据源 ──────────────────────────────────────────
FEATURE_COLS_JSON = PROJECT_ROOT / "models/production/e1-conservative/feature_cols.json"
E1_IMPORTANCE_CSV = PROJECT_ROOT / "experiments/weekly/weekly_bear_v0305_E1_decontam/feature_importance.csv"
E8_IMPORTANCE_CSV = PROJECT_ROOT / "experiments/weekly/weekly_bear_v0305_E8_touch_label/feature_importance.csv"
OUTPUT_CSV = PROJECT_ROOT / "docs/specs/feature_dictionary.csv"


# ──────────────────────────────────────────────────────
# 特征分类规则
# ──────────────────────────────────────────────────────
# 元组: (匹配函数, category, subcategory, source_module, formula, description)
# 按顺序匹配, 第一个命中即采纳。
# ──────────────────────────────────────────────────────
import re


def _w(name: str) -> str:
    """从特征名末尾抽取窗口长度（数字）, 用于动态描述."""
    m = re.search(r"(\d+)", name)
    return m.group(1) if m else "?"


def classify(name: str) -> dict:
    """根据特征名返回分类元数据."""
    n = name

    # ============ 技术指标: 移动平均 ============
    if re.fullmatch(r"sma_\d+", n):
        w = _w(n)
        return dict(category="技术指标", subcategory="简单移动平均(SMA)",
                    source_module="src/features/technical.py",
                    formula=f"close.rolling({w}).mean()",
                    description=f"过去 {w} 日收盘价简单算术平均，代表中长期趋势中枢")

    if re.fullmatch(r"ema_\d+", n):
        w = _w(n)
        return dict(category="技术指标", subcategory="指数移动平均(EMA)",
                    source_module="src/features/technical.py",
                    formula=f"close.ewm(span={w}).mean()",
                    description=f"过去 {w} 日指数加权均价，权重按 (1-α)^k 衰减，对近期价格更敏感")

    if re.fullmatch(r"sma_cross_\d+_\d+", n):
        parts = re.findall(r"\d+", n)
        a, b = parts[0], parts[1]
        return dict(category="技术指标", subcategory="均线交叉",
                    source_module="src/features/technical.py",
                    formula=f"sma_{a} - sma_{b}",
                    description=f"短期 SMA{a} 与长期 SMA{b} 之差，>0 多头排列 / <0 空头排列")

    if n.startswith("price_vs_sma_"):
        w = _w(n)
        return dict(category="技术指标", subcategory="价格相对均线",
                    source_module="src/features/technical.py",
                    formula=f"(close - sma_{w}) / sma_{w}",
                    description=f"价格偏离 SMA{w} 的百分比，正=超买 / 负=超卖")

    # ============ 技术指标: 振荡器 ============
    if re.fullmatch(r"rsi_\d+", n):
        w = _w(n)
        return dict(category="技术指标", subcategory="RSI 相对强弱",
                    source_module="src/features/technical.py",
                    formula=f"100 - 100/(1 + avg_gain_{w}/avg_loss_{w})",
                    description=f"{w} 日相对强弱指数, [0,100], >70 超买 / <30 超卖")

    if n == "macd":
        return dict(category="技术指标", subcategory="MACD",
                    source_module="src/features/technical.py",
                    formula="ema_12 - ema_26",
                    description="MACD 快慢线之差, 衡量动量方向")
    if n == "macd_signal":
        return dict(category="技术指标", subcategory="MACD",
                    source_module="src/features/technical.py",
                    formula="macd.ewm(span=9).mean()",
                    description="MACD 9 期 EMA 平滑信号线")
    if n == "macd_hist":
        return dict(category="技术指标", subcategory="MACD",
                    source_module="src/features/technical.py",
                    formula="macd - macd_signal",
                    description="MACD 柱状图 (动量加速度), 由负转正=底部信号")

    if n.startswith("bb_upper_"):
        w = _w(n)
        return dict(category="技术指标", subcategory="布林带",
                    source_module="src/features/technical.py",
                    formula=f"sma_{w} + 2 * std_{w}",
                    description=f"布林带上轨, 价格触及通常视为短期阻力")
    if n.startswith("bb_lower_"):
        w = _w(n)
        return dict(category="技术指标", subcategory="布林带",
                    source_module="src/features/technical.py",
                    formula=f"sma_{w} - 2 * std_{w}",
                    description="布林带下轨, 价格触及通常视为短期支撑")
    if n.startswith("bb_width_"):
        w = _w(n)
        return dict(category="技术指标", subcategory="布林带",
                    source_module="src/features/technical.py",
                    formula=f"(bb_upper_{w} - bb_lower_{w}) / sma_{w}",
                    description="布林带宽度, 反映波动率水平, 收窄→突破前夜")
    if n.startswith("bb_pctb_"):
        w = _w(n)
        return dict(category="技术指标", subcategory="布林带",
                    source_module="src/features/technical.py",
                    formula=f"(close - bb_lower_{w}) / (bb_upper_{w} - bb_lower_{w})",
                    description="价格在布林带中的相对位置, 0=下轨 / 1=上轨")

    if re.fullmatch(r"atr_\d+", n):
        w = _w(n)
        return dict(category="技术指标", subcategory="ATR 真实波动",
                    source_module="src/features/technical.py",
                    formula=f"TR.rolling({w}).mean(), TR=max(H-L, |H-C₋₁|, |L-C₋₁|)",
                    description=f"{w} 日平均真实波动幅度, 绝对值, 用于止损宽度参考")
    if re.fullmatch(r"atr_pct_\d+", n):
        w = _w(n)
        return dict(category="技术指标", subcategory="ATR 真实波动",
                    source_module="src/features/technical.py",
                    formula=f"atr_{w} / close",
                    description="ATR 占价格百分比, 跨币种/跨价位可比的波动指标")

    # ============ 技术指标: 动量 / 波动 / 极值 ============
    if re.fullmatch(r"return_\d+d", n):
        w = _w(n)
        return dict(category="技术指标", subcategory="收益率",
                    source_module="src/features/technical.py",
                    formula=f"close.pct_change({w})",
                    description=f"过去 {w} 日累计收益率")
    if re.fullmatch(r"volatility_\d+d", n):
        w = _w(n)
        return dict(category="技术指标", subcategory="波动率",
                    source_module="src/features/technical.py",
                    formula=f"close.pct_change().rolling({w}).std()",
                    description=f"过去 {w} 日日收益率标准差")
    if re.fullmatch(r"high_\d+d_dist", n):
        w = _w(n)
        return dict(category="技术指标", subcategory="极值距离",
                    source_module="src/features/technical.py",
                    formula=f"(close - high.rolling({w}).max()) / close",
                    description=f"距 {w} 日最高价的百分比, 0=刚创新高 / 负=回撤")
    if re.fullmatch(r"low_\d+d_dist", n):
        w = _w(n)
        return dict(category="技术指标", subcategory="极值距离",
                    source_module="src/features/technical.py",
                    formula=f"(close - low.rolling({w}).min()) / close",
                    description=f"距 {w} 日最低价的百分比, 衡量反弹强度")
    if n.startswith("stoch_k_"):
        w = _w(n)
        return dict(category="技术指标", subcategory="KD 随机",
                    source_module="src/features/technical.py",
                    formula=f"100 * (close - low_{w}) / (high_{w} - low_{w})",
                    description=f"{w} 日 K 值, [0,100], 超买/超卖振荡器")
    if n.startswith("stoch_d_"):
        return dict(category="技术指标", subcategory="KD 随机",
                    source_module="src/features/technical.py",
                    formula="stoch_k.rolling(3).mean()",
                    description="K 值的 3 期均值平滑, 减少噪声")

    # ============ 量能: 成交量均线/比率/变化 ============
    if re.fullmatch(r"vol_sma_\d+", n):
        w = _w(n)
        return dict(category="量能", subcategory="成交量均线",
                    source_module="src/features/volume.py",
                    formula=f"volume.rolling({w}).mean()",
                    description=f"{w} 日成交量算术均值")
    if re.fullmatch(r"vol_ratio_\d+", n):
        w = _w(n)
        return dict(category="量能", subcategory="成交量比率",
                    source_module="src/features/volume.py",
                    formula=f"volume / vol_sma_{w}",
                    description=f"当日成交量与 {w} 日均量之比, >1 放量 / <1 缩量")
    if re.fullmatch(r"vol_change_\d+d", n):
        w = _w(n)
        return dict(category="量能", subcategory="成交量变化",
                    source_module="src/features/volume.py",
                    formula=f"volume.pct_change({w})",
                    description=f"过去 {w} 日成交量变化率")
    if re.fullmatch(r"vol_volatility_\d+", n):
        w = _w(n)
        return dict(category="量能", subcategory="成交量波动",
                    source_module="src/features/volume.py",
                    formula=f"volume.pct_change().rolling({w}).std()",
                    description=f"{w} 日成交量波动率, 高 = 资金流动不稳定")
    if re.fullmatch(r"vol_price_corr_\d+", n):
        w = _w(n)
        return dict(category="量能", subcategory="量价相关",
                    source_module="src/features/volume.py",
                    formula=f"volume.rolling({w}).corr(close)",
                    description=f"{w} 日量价滚动相关系数, 正=共振上涨 / 负=背离")

    # ============ 量能: OBV / VWAP ============
    if n == "obv":
        return dict(category="量能", subcategory="OBV",
                    source_module="src/features/volume.py",
                    formula="(sign(close.diff()) * volume).cumsum()",
                    description="On-Balance Volume, 累积净成交量, 衡量资金累积/派发")
    if n.startswith("obv_sma_"):
        w = _w(n)
        return dict(category="量能", subcategory="OBV",
                    source_module="src/features/volume.py",
                    formula=f"obv.rolling({w}).mean()",
                    description=f"OBV {w} 日均线, 用于趋势确认")
    if re.fullmatch(r"vwap_\d+", n):
        w = _w(n)
        return dict(category="量能", subcategory="VWAP",
                    source_module="src/features/volume.py",
                    formula=f"sum(typical_price * vol) / sum(vol) over {w} days",
                    description=f"{w} 日成交量加权平均价 (typical=(H+L+C)/3)")
    if n.startswith("price_vs_vwap_"):
        w = _w(n)
        return dict(category="量能", subcategory="VWAP",
                    source_module="src/features/volume.py",
                    formula=f"(close - vwap_{w}) / vwap_{w}",
                    description=f"价格偏离 {w} 日 VWAP 的百分比, 衡量大资金成本线偏离度")

    # ============ 资金流 (flow.py) ============
    if re.fullmatch(r"flow_change_\d+d", n):
        w = _w(n)
        return dict(category="资金流", subcategory="资金流变化率",
                    source_module="src/features/flow.py",
                    formula=f"quote_volume.pct_change({w})",
                    description=f"{w} 日成交额变化率 (USDT 计价资金流入/流出强度)")
    if re.fullmatch(r"flow_momentum_\d+", n):
        w = _w(n)
        return dict(category="资金流", subcategory="资金流动量",
                    source_module="src/features/flow.py",
                    formula=f"quote_volume.rolling({w}).mean().pct_change({w})",
                    description=f"{w} 日均资金流的环比变化, 衡量资金趋势加速/衰减")
    if re.fullmatch(r"flow_price_divergence_\d+", n):
        w = _w(n)
        return dict(category="资金流", subcategory="量价背离",
                    source_module="src/features/flow.py",
                    formula=f"qv.pct_change({w}) - close.pct_change({w})",
                    description=f"{w} 日资金流变化 - 价格变化, 正=放量上涨/缩量下跌 (健康)")
    if n == "volume_density":
        return dict(category="资金流", subcategory="成交密度",
                    source_module="src/features/flow.py + market_structure.py",
                    formula="volume / (high - low)",
                    description="单位价格区间承接的成交量, 高=阻力强 / 低=易突破")
    if n.startswith("volume_density_sma_"):
        w = _w(n)
        return dict(category="资金流", subcategory="成交密度",
                    source_module="src/features/flow.py",
                    formula=f"volume_density.rolling({w}).mean()",
                    description=f"成交密度 {w} 日均值 (flow 模块版)")
    if n.startswith("volume_density_ma_"):
        w = _w(n)
        return dict(category="资金流", subcategory="成交密度",
                    source_module="src/features/market_structure.py",
                    formula=f"volume_density.rolling({w}).mean()",
                    description=f"成交密度 {w} 日均值 (market_structure 模块版, 与 _sma_ 重复)")
    if n.startswith("avg_trade_size_sma_"):
        w = _w(n)
        return dict(category="资金流", subcategory="单笔成交规模",
                    source_module="src/features/flow.py",
                    formula=f"(volume / trades).rolling({w}).mean()",
                    description=f"{w} 日均单笔成交量 (flow 模块版, 与 _ma_ 重复)")
    if n.startswith("avg_trade_size_ratio_"):
        w = _w(n)
        return dict(category="资金流", subcategory="单笔成交规模",
                    source_module="src/features/flow.py + market_structure.py",
                    formula=f"avg_trade_size / avg_trade_size_sma_{w}",
                    description=f"当日单笔规模与 {w} 日均值之比, >1 大单进场")

    # ============ 市场结构 (market_structure.py) ============
    if re.fullmatch(r"funding_rate_\d+", n):
        w = _w(n)
        return dict(category="市场结构", subcategory="模拟资金费率",
                    source_module="src/features/market_structure.py",
                    formula=f"close.pct_change().rolling({w}).mean() * 100",
                    description=f"基于价格动量模拟的 {w} 日资金费率代理 (无外部 OI 数据时使用)")
    if re.fullmatch(r"open_interest_\d+", n):
        w = _w(n)
        return dict(category="市场结构", subcategory="模拟持仓量",
                    source_module="src/features/market_structure.py",
                    formula=f"volume.rolling({w}).sum()",
                    description=f"基于成交量累积模拟的 {w} 日 OI 代理")
    if n == "cvd":
        return dict(category="市场结构", subcategory="CVD",
                    source_module="src/features/market_structure.py",
                    formula="(sign(close - open) * volume).cumsum()",
                    description="累积成交量差 (Cumulative Volume Delta), 净买卖压力")
    if n.startswith("cvd_ma_"):
        w = _w(n)
        return dict(category="市场结构", subcategory="CVD",
                    source_module="src/features/market_structure.py",
                    formula=f"cvd.rolling({w}).mean()",
                    description=f"CVD {w} 日均值")
    if n.startswith("cvd_change_"):
        w = _w(n)
        return dict(category="市场结构", subcategory="CVD",
                    source_module="src/features/market_structure.py",
                    formula=f"cvd.pct_change({w})",
                    description=f"CVD {w} 日变化率, 衡量买卖力量切换速度")
    if n == "stablecoin_inflow_proxy":
        return dict(category="市场结构", subcategory="稳定币流入代理",
                    source_module="src/features/market_structure.py",
                    formula="-close.pct_change(7) * volume.rolling(7).mean()",
                    description="价格下跌时放量 → 推测稳定币入场抄底 (无链上数据时的代理)")
    if n == "buy_pressure":
        return dict(category="市场结构", subcategory="买入压力",
                    source_module="src/features/market_structure.py",
                    formula="(close - low) / (high - low)",
                    description="K 线买入压力: 收盘越靠近最高价 → 多头掌控")
    if n.startswith("buy_pressure_ma_"):
        w = _w(n)
        return dict(category="市场结构", subcategory="买入压力",
                    source_module="src/features/market_structure.py",
                    formula=f"buy_pressure.rolling({w}).mean()",
                    description=f"买压 {w} 日均值, 平滑后看趋势性多/空")
    if re.fullmatch(r"qvol_sma_\d+", n):
        w = _w(n)
        return dict(category="市场结构", subcategory="USDT 成交额",
                    source_module="src/features/market_structure.py + flow.py",
                    formula=f"quote_volume.rolling({w}).mean()",
                    description=f"{w} 日 USDT 计价成交额均线")
    if re.fullmatch(r"qvol_ratio_\d+", n):
        w = _w(n)
        return dict(category="市场结构", subcategory="USDT 成交额",
                    source_module="src/features/market_structure.py + flow.py",
                    formula=f"quote_volume / qvol_sma_{w}",
                    description=f"当日 USDT 额与 {w} 日均值之比")
    if re.fullmatch(r"trades_sma_\d+", n):
        w = _w(n)
        return dict(category="市场结构", subcategory="交易笔数",
                    source_module="src/features/market_structure.py + flow.py",
                    formula=f"trades.rolling({w}).mean()",
                    description=f"{w} 日均交易笔数 (反映参与者活跃度)")
    if re.fullmatch(r"trades_ratio_\d+", n):
        w = _w(n)
        return dict(category="市场结构", subcategory="交易笔数",
                    source_module="src/features/market_structure.py + flow.py",
                    formula=f"trades / trades_sma_{w}",
                    description=f"当日笔数与 {w} 日均值之比, 突然放笔=情绪起伏")
    if re.fullmatch(r"trades_change_\d+d", n):
        w = _w(n)
        return dict(category="市场结构", subcategory="交易笔数",
                    source_module="src/features/market_structure.py + flow.py",
                    formula=f"trades.pct_change({w})",
                    description=f"{w} 日交易笔数变化率")
    if n == "avg_trade_size":
        return dict(category="市场结构", subcategory="单笔成交规模",
                    source_module="src/features/market_structure.py + flow.py",
                    formula="volume / trades",
                    description="单笔平均成交量, 高=大户主导 / 低=散户主导")
    if n.startswith("avg_trade_size_ma_"):
        w = _w(n)
        return dict(category="市场结构", subcategory="单笔成交规模",
                    source_module="src/features/market_structure.py",
                    formula=f"avg_trade_size.rolling({w}).mean()",
                    description=f"{w} 日均单笔成交量 (market_structure 版)")

    # ============ 外部数据: FGI 恐惧贪婪指数 ============
    if n == "ext_fgi":
        return dict(category="外部数据", subcategory="FGI 恐惧贪婪",
                    source_module="src/features/external.py",
                    formula="alternative.me API → reindex(ffill)",
                    description="Crypto Fear & Greed Index, [0,100], 0=极度恐惧 / 100=极度贪婪")
    if re.fullmatch(r"ext_fgi_ma\d+", n):
        w = _w(n)
        return dict(category="外部数据", subcategory="FGI 恐惧贪婪",
                    source_module="src/features/external.py",
                    formula=f"ext_fgi.rolling({w}).mean()",
                    description=f"FGI {w} 日均值, 平滑情绪波动")
    if re.fullmatch(r"ext_fgi_change_\d+d", n):
        w = _w(n)
        return dict(category="外部数据", subcategory="FGI 恐惧贪婪",
                    source_module="src/features/external.py",
                    formula=f"ext_fgi.pct_change({w})",
                    description=f"FGI {w} 日变化率, 衡量情绪转向速度")
    if n == "ext_fgi_std_14":
        return dict(category="外部数据", subcategory="FGI 恐惧贪婪",
                    source_module="src/features/external.py",
                    formula="ext_fgi.rolling(14).std()",
                    description="FGI 14 日标准差, 情绪波动率, 高=市场分歧大")
    if n == "ext_fgi_extreme_fear":
        return dict(category="外部数据", subcategory="FGI 恐惧贪婪",
                    source_module="src/features/external.py",
                    formula="(ext_fgi < 25).astype(int)",
                    description="极度恐惧标记 (0/1), 历史上 = 反弹机会窗口")
    if n == "ext_fgi_extreme_greed":
        return dict(category="外部数据", subcategory="FGI 恐惧贪婪",
                    source_module="src/features/external.py",
                    formula="(ext_fgi > 75).astype(int)",
                    description="极度贪婪标记 (0/1), 历史上 = 顶部风险信号")
    if n == "ext_fgi_price_divergence":
        return dict(category="外部数据", subcategory="FGI 恐惧贪婪",
                    source_module="src/features/external.py",
                    formula="ext_fgi.pct_change(7) - close.pct_change(7)",
                    description="情绪与价格背离 (7d), 价格涨但情绪转空 → 潜在顶部")

    # ============ 兜底 ============
    return dict(category="未分类", subcategory="?",
                source_module="?",
                formula="?",
                description=f"未识别的特征模式: {n}")


# ──────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────
def main():
    cols = json.loads(FEATURE_COLS_JSON.read_text())["feature_cols"]
    fi_e1 = pd.read_csv(E1_IMPORTANCE_CSV).set_index("feature")["importance"]
    fi_e8 = pd.read_csv(E8_IMPORTANCE_CSV).set_index("feature")["importance"]

    total_e1 = fi_e1.sum()
    total_e8 = fi_e8.sum()
    rank_e1 = fi_e1.rank(method="min", ascending=False).astype(int)
    rank_e8 = fi_e8.rank(method="min", ascending=False).astype(int)

    rows = []
    for col in cols:
        info = classify(col)
        imp_e1 = int(fi_e1.get(col, 0))
        imp_e8 = int(fi_e8.get(col, 0))
        rows.append({
            "feature_name": col,
            "category": info["category"],
            "subcategory": info["subcategory"],
            "source_module": info["source_module"],
            "formula": info["formula"],
            "description": info["description"],
            "importance_e1": imp_e1,
            "rank_e1": int(rank_e1.get(col, 0)),
            "pct_e1": round(imp_e1 / total_e1 * 100, 2) if total_e1 else 0.0,
            "importance_e8": imp_e8,
            "rank_e8": int(rank_e8.get(col, 0)),
            "pct_e8": round(imp_e8 / total_e8 * 100, 2) if total_e8 else 0.0,
        })

    df = pd.DataFrame(rows)
    # 按 E1+E8 总重要性降序排序方便 review
    df["_sort"] = df["importance_e1"] + df["importance_e8"]
    df = df.sort_values("_sort", ascending=False).drop(columns="_sort").reset_index(drop=True)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    # ── 终端摘要 ──
    print(f"✅ 特征字典已导出: {OUTPUT_CSV}")
    print(f"   共 {len(df)} 个特征, 跨 {df['category'].nunique()} 个大类:")
    for cat, grp in df.groupby("category"):
        print(f"   - {cat}: {len(grp)} 个 (E1 重要性占比 {grp['pct_e1'].sum():.1f}% / E8 {grp['pct_e8'].sum():.1f}%)")
    n_unclassified = (df["category"] == "未分类").sum()
    if n_unclassified:
        print(f"   ⚠️  未分类: {n_unclassified} 个")
        print(df[df["category"] == "未分类"]["feature_name"].tolist())

    # 找出两个模型都不用 (importance=0) 的低价值特征
    zero_both = df[(df["importance_e1"] == 0) & (df["importance_e8"] == 0)]
    if len(zero_both):
        print(f"\n💡 E1+E8 重要性都为 0 (候选移除): {len(zero_both)} 个")
        for name in zero_both["feature_name"].head(20):
            print(f"   - {name}")


if __name__ == "__main__":
    main()
