"""顶部研判数据层 — 三层精英制危险分级 (Layer A/B/C).

实证依据见 docs/reports/btc_topping_ic_analysis_20260608.html:
  - Layer A 主信号: Reserve Risk (唯一 |t|>=2 的真 alpha)
  - Layer B 确认:   LTH-MVRV(首选)/LTH-SOPR/LTH-NUPL/MVRV-Z/Puell (Regime 依赖)
  - Layer C 触发:   SMA50 破位 / 周线 MACD 转负 / 吊灯止损 (仅 A/B 警报后激活)

全程 expanding 历史分位 (point-in-time, 只用 <=当日数据), 不用绝对阈值。
纯只读展示层, 不碰模型/不下单 (沿用 dashboard 原则)。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ONCHAIN_DIR = PROJECT_ROOT / "data" / "external" / "onchain"

# Layer B 确认信号 (name -> csv 文件名), LTH-MVRV 为实证首选
LAYER_B = [
    ("LTH-MVRV", "lth_mvrv.csv", True),   # 首选 (90d IC -0.296)
    ("LTH-SOPR", "lth_sopr.csv", False),
    ("LTH-NUPL", "lth_nupl.csv", False),
    ("MVRV-Z", "mvrv_zscore_data.csv", False),
    ("Puell", "puell_multiple_data.csv", False),
]
# 分批撤退计划 (与框架 §5.1 一致)
BATCHES = [("第1批", 30), ("第2批", 30), ("第3批", 40)]


def _load(path: Path, col: str = "value") -> pd.Series | None:
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
        s = df[col] if col in df.columns else df.iloc[:, 0]
        return s[~s.index.duplicated(keep="last")].dropna()
    except (OSError, ValueError, KeyError):
        return None


def _expanding_pct(s: pd.Series) -> pd.Series:
    """每个点的 expanding 历史分位 (0~100), 只用 <=当日数据 (防未来函数)."""
    return s.expanding(min_periods=1).apply(
        lambda w: (w <= w.iloc[-1]).sum() / len(w) * 100.0, raw=False
    )


def _latest_pct(s: pd.Series | None) -> float | None:
    if s is None or s.empty:
        return None
    return round(float((s <= s.iloc[-1]).sum() / len(s) * 100.0), 1)


def _layer_c() -> list[dict]:
    """Layer C 技术面触发 (SMA50 破位 / 周线 MACD 转负 / 吊灯止损)."""
    try:
        from src.performance.backfill import load_ohlcv
        df = load_ohlcv()
    except (OSError, ValueError, ImportError):
        return [{"name": n, "fired": None} for n in
                ("跌破 SMA50", "周线 MACD 转负", "吊灯止损触发")]
    close, high, low = df["close"], df["high"], df["low"]
    # SMA50 破位
    sma50 = close.rolling(50).mean()
    below_sma = bool(close.iloc[-1] < sma50.iloc[-1]) if len(close) >= 50 else None
    # 周线 MACD 柱转负 (用周线收盘)
    wk = close.resample("W").last()
    macd = wk.ewm(span=12).mean() - wk.ewm(span=26).mean()
    hist = macd - macd.ewm(span=9).mean()
    macd_neg = bool(hist.iloc[-1] < 0) if len(hist) >= 3 else None
    # 吊灯止损 (22 周期最高价 - 3*ATR22)
    tr = pd.concat([high - low, (high - close.shift()).abs(),
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(22).mean()
    chand = high.rolling(22).max() - 3 * atr
    chand_hit = bool(close.iloc[-1] < chand.iloc[-1]) if len(close) >= 22 else None
    return [
        {"name": "跌破 SMA50", "fired": below_sma},
        {"name": "周线 MACD 转负", "fired": macd_neg},
        {"name": "吊灯止损触发", "fired": chand_hit},
    ]


def _classify(rr_pct: float | None, lb_high: int, lc_fired: int) -> dict:
    """危险分级 (框架 §5.1). 返回等级/动作/目标仓位/应减批次."""
    if rr_pct is None:
        return {"key": "unknown", "label": "数据缺失", "color": "#94a3b8",
                "action": "Reserve Risk 数据不可用", "target": None, "sold": 0}
    if rr_pct >= 95 and lb_high >= 3:
        sold = 3 if lc_fired >= 1 else 2
        return {"key": "crit", "label": "极危", "color": "#f43f5e",
                "action": "减第 2 批" + ("，Layer C 已触发→清第 3 批" if lc_fired else "（等 Layer C 清第 3 批）"),
                "target": 100 - sum(p for _, p in BATCHES[:sold]), "sold": sold}
    if rr_pct >= 85 and lb_high >= 2:
        return {"key": "danger", "label": "危险", "color": "#f59e0b",
                "action": "分批减仓第 1 批 (~30%)", "target": 70, "sold": 1}
    if rr_pct >= 70:
        return {"key": "warn", "label": "警示", "color": "#fbbf24",
                "action": "停止加仓，开始盯 Layer C", "target": 100, "sold": 0}
    return {"key": "safe", "label": "安全", "color": "#10b981",
            "action": "满仓持有", "target": 100, "sold": 0}


def build(hist_points: int = 120) -> dict:
    """组装顶部页 context: Layer A/B/C 读数 + 分级 + 历史回放序列."""
    rr = _load(ONCHAIN_DIR / "reserve_risk.csv")
    rr_pct = _latest_pct(rr)
    rr_val = round(float(rr.iloc[-1]), 6) if rr is not None and not rr.empty else None

    # Layer B
    lb_rows = []
    for name, fname, preferred in LAYER_B:
        pct = _latest_pct(_load(ONCHAIN_DIR / fname))
        lb_rows.append({"name": name, "pct": pct, "preferred": preferred,
                        "high": (pct is not None and pct >= 85)})
    lb_high = sum(1 for r in lb_rows if r["high"])

    # Layer C
    lc_rows = _layer_c()
    lc_fired = sum(1 for r in lc_rows if r["fired"])
    lc_active = (rr_pct is not None and rr_pct >= 85 and lb_high >= 2)

    verdict = _classify(rr_pct, lb_high, lc_fired)

    # 历史回放 (RR expanding 分位 + 价格, 抽稀到 hist_points)
    hist = {"dates": [], "rr_pct": [], "price": [], "fire": []}
    if rr is not None and not rr.empty:
        rr_pct_series = _expanding_pct(rr)
        step = max(1, len(rr_pct_series) // hist_points)
        sampled = rr_pct_series.iloc[::step]
        try:
            from src.performance.backfill import load_ohlcv
            price = load_ohlcv()["close"]
        except (OSError, ValueError, ImportError):
            price = pd.Series(dtype=float)
        for d, p in sampled.items():
            hist["dates"].append(d.strftime("%Y-%m-%d"))
            hist["rr_pct"].append(round(float(p), 1))
            px = price.asof(d) if not price.empty else None
            hist["price"].append(round(float(px), 0) if px == px and px is not None else None)
            hist["fire"].append(round(float(p), 1) if p >= 85 else None)

    batches = [{"name": n, "pct": p, "done": i < verdict["sold"]}
               for i, (n, p) in enumerate(BATCHES)]

    return {
        "rr_val": rr_val, "rr_pct": rr_pct,
        "lb_rows": lb_rows, "lb_high": lb_high,
        "lc_rows": lc_rows, "lc_active": lc_active, "lc_fired": lc_fired,
        "verdict": verdict, "batches": batches, "hist": hist,
    }
