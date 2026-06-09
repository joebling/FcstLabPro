"""周期研判共享内核 — 顶部/底部双向复用 (DRY).

顶部(逃顶)与底部(抄底)共享同一套 expanding 分位引擎、技术面触发、历史回放骨架，
仅 direction 不同:
  - direction="top"    : 高分位=危险 (Reserve Risk 等越高越接近顶)
  - direction="bottom" : 低分位=机会 (估值类越低越接近底)

实证依据:
  - 顶部: docs/reports/btc_topping_ic_analysis_20260608.html
  - 底部: docs/reports/btc_bottoming_ic_analysis_20260608.html (V2 事件级校准)

方法论铁律 (与研究脚本同口径):
  - 全程 expanding 历史分位 (point-in-time, 只用 <=当日数据), 不用绝对阈值。
  - 纯只读展示层, 不碰模型/不下单。
  - Layer C 技术面方向随 direction 翻转 (顶部破位看跌 / 底部站上看涨)。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ONCHAIN_DIR = PROJECT_ROOT / "data" / "external" / "onchain"
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"


# ---------- 数据加载 ----------
def load_series(path: Path, col: str = "value") -> pd.Series | None:
    """读单列时序 (date 索引, 去重去 NaN), 文件缺失/损坏返回 None。"""
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
        s = df[col] if col in df.columns else df.iloc[:, 0]
        return s[~s.index.duplicated(keep="last")].dropna()
    except (OSError, ValueError, KeyError):
        return None


def load_onchain(fname: str, col: str = "value") -> pd.Series | None:
    """便捷: 从 data/external/onchain/ 读链上指标。"""
    return load_series(ONCHAIN_DIR / fname, col)


# ---------- 分位引擎 (point-in-time, 防未来函数) ----------
def expanding_pct(s: pd.Series) -> pd.Series:
    """每个点的 expanding 历史分位 (0~100), 只用 <=当日数据。"""
    return s.expanding(min_periods=1).apply(
        lambda w: (w <= w.iloc[-1]).sum() / len(w) * 100.0, raw=False
    )


def latest_pct(s: pd.Series | None) -> float | None:
    """最新值在自身历史中的 expanding 分位 (0~100)。"""
    if s is None or s.empty:
        return None
    return round(float((s <= s.iloc[-1]).sum() / len(s) * 100.0), 1)


# ---------- Layer C 技术面触发 (方向相关) ----------
def layer_c_signals(direction: str) -> list[dict]:
    """技术面择时触发. 顶部看跌破位, 底部看右侧确认 (站上/转正/放量突破).

    顶部: 跌破 SMA50 / 周线 MACD 转负 / 吊灯止损触发
    底部: 站上 SMA50 / 周线 MACD 转正 / 放量突破 (右侧确认, 防接飞刀)
    """
    is_bottom = direction == "bottom"
    names = (
        ["站上 SMA50", "周线 MACD 转正", "放量突破前高"]
        if is_bottom
        else ["跌破 SMA50", "周线 MACD 转负", "吊灯止损触发"]
    )
    try:
        from src.dashboard.data import load_display_ohlcv
        df, _ = load_display_ohlcv()
    except (OSError, ValueError, ImportError):
        return [{"name": n, "fired": None} for n in names]

    close, high, low = df["close"], df["high"], df["low"]
    vol = df["volume"] if "volume" in df.columns else None

    # 1) SMA50 站上/跌破
    sma50 = close.rolling(50).mean()
    if len(close) >= 50:
        above = bool(close.iloc[-1] > sma50.iloc[-1])
        sig1 = above if is_bottom else (not above)
    else:
        sig1 = None

    # 2) 周线 MACD 柱 转正/转负
    wk = close.resample("W").last()
    macd = wk.ewm(span=12).mean() - wk.ewm(span=26).mean()
    hist = macd - macd.ewm(span=9).mean()
    if len(hist) >= 3:
        pos = bool(hist.iloc[-1] > 0)
        sig2 = pos if is_bottom else (not pos)
    else:
        sig2 = None

    # 3) 底部: 放量突破前高 / 顶部: 吊灯止损
    if is_bottom:
        if len(close) >= 20:
            breakout = bool(close.iloc[-1] > high.rolling(20).max().shift(1).iloc[-1])
            if vol is not None and len(vol) >= 20:
                vol_ok = bool(vol.iloc[-1] > vol.rolling(20).mean().iloc[-1] * 1.3)
                sig3 = breakout and vol_ok
            else:
                sig3 = breakout  # 无成交量数据时仅看突破
        else:
            sig3 = None
    else:
        tr = pd.concat(
            [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(22).mean()
        chand = high.rolling(22).max() - 3 * atr
        sig3 = bool(close.iloc[-1] < chand.iloc[-1]) if len(close) >= 22 else None

    return [
        {"name": names[0], "fired": sig1},
        {"name": names[1], "fired": sig2},
        {"name": names[2], "fired": sig3},
    ]


# ---------- 历史点灯回放 (方向相关) ----------
def replay_history(
    driver: pd.Series, fire_threshold: float, direction: str, hist_points: int = 120
) -> dict:
    """driver 的 expanding 分位曲线 + 价格叠加 + 点灯标记.

    顶部: 分位 >= fire_threshold 点灯 (危险); 底部: 分位 <= fire_threshold 点灯 (机会)。
    抽稀到约 hist_points 个点。
    """
    hist = {"dates": [], "pct": [], "price": [], "fire": []}
    if driver is None or driver.empty:
        return hist
    pct_series = expanding_pct(driver)
    step = max(1, len(pct_series) // hist_points)
    sampled = pct_series.iloc[::step]
    try:
        from src.dashboard.data import load_display_ohlcv
        price = load_display_ohlcv()[0]["close"]
    except (OSError, ValueError, ImportError):
        price = pd.Series(dtype=float)
    is_bottom = direction == "bottom"
    for d, p in sampled.items():
        hist["dates"].append(d.strftime("%Y-%m-%d"))
        hist["pct"].append(round(float(p), 1))
        px = price.asof(d) if not price.empty else None
        hist["price"].append(round(float(px), 0) if px == px and px is not None else None)
        fired = (p <= fire_threshold) if is_bottom else (p >= fire_threshold)
        hist["fire"].append(round(float(p), 1) if fired else None)
    return hist
