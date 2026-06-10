#!/usr/bin/env python3
"""ahr999 定投指数 — 纯公式计算 (无需付费 API), 输出全历史序列.

ahr999 (作者 ahr999, 微博) 衡量 BTC 是否处于"定投/抄底"区:
    ahr999 = (现价 / 200日定投成本) * (现价 / 指数增长估值)
      200日定投成本 = 近 200 日收盘价的 [几何均值]  (= exp(mean(ln close)))
      指数增长估值  = 10^(5.84 * log10(币龄) - 17.01)
      币龄          = 距创世块 2009-01-03 的天数

区间 (作者原始划分):
    < 0.45  抄底区   |  0.45-1.2 定投区  |  1.2-5 观望区  |  >= 5 泡沫区

为何是纯计算而非下载:
    本指标只依赖日线价格 (我们每天已下载 data/live/btc_*.csv), 不碰任何付费/会断供的
    链上 API。可完全复现、可 IC 验证 (手册铁律), 比依赖第三方端点更稳。

数据范围:
    价格源 = data/live/ (实时, 跟生产 pipeline 同源, 拿最新收盘) 为主
             + data/raw/ 补 live 起点之前的旧史 (冻结基准, 2018 起)。
    200日窗口 => ahr999 从约 2018-07 起。加 --coingecko 可再前置拉 CoinGecko 全量
    日线 (约 2013 起), 把序列拓到含 2015 周期底, IC 验证样本更全。
    (live 缺失时自动回退到 data/raw/ 并告警 — 本地开发机常见, 生产不应出现。)

注意 (与 fuckbtc.com 实现的差异):
    Fish 的看板用 200 日 [算术均值] 近似定投成本; 本脚本用 [几何均值] (作者原始定义,
    更贴"等额定投成本")。两者数值接近但非 bit-identical, 这里以原始定义为准。

用法:
    python scripts/compute_ahr999.py                 # 用本地价格算, 写 ahr999.csv
    python scripts/compute_ahr999.py --coingecko     # 先拉 CoinGecko 全量再算 (更长)
    python scripts/compute_ahr999.py --dry-run       # 只算不写, 打印尾部 + 当前区间
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

# 生产价格源走 serving 单一真相源 (lesson_0602): data/live/ 为主 (实时, 跟 pipeline
# 同源), data/raw/ 只用来补 live 起点之前的旧史 (冻结基准, 起点更早)。
# 历史 bug: 这里硬编码读 data/raw/ -> ahr999 永远停在训练基准末日 (滞后数天)。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from src.serving.paths import (  # noqa: E402
    BASELINE_OHLCV_PATH,
    EXTERNAL_DIR,
    LIVE_OHLCV_PATH,
)

OUTPUT_CSV = EXTERNAL_DIR / "onchain" / "ahr999.csv"
GENESIS = dt.date(2009, 1, 3)            # BTC 创世块
DCA_WINDOW = 200                         # 定投成本窗口 (天)
EXP_A, EXP_B = 5.84, -17.01              # 指数增长估值拟合常数 (作者原始)
COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    "?vs_currency=usd&days=max"
)
HTTP_TIMEOUT = 30
USER_AGENT = "FcstLabPro/0.1 (research; ahr999)"


def load_price_csv(path: Path) -> pd.Series:
    """读任意日线 CSV 收盘价 -> Series(index=date, value=close)。"""
    if not path.exists():
        raise FileNotFoundError(f"找不到价格文件: {path}")
    df = pd.read_csv(path, parse_dates=["date"])
    s = df.set_index(df["date"].dt.date)["close"].astype(float)
    s.index.name = "date"
    return s.sort_index()


def load_live_price() -> tuple[pd.Series, str]:
    """生产 live 价格 (data/live/); 缺失时回退训练基准 (data/raw/) 并告警。

    返回 (series, source_label)。VPS 上 live 每日下载, 本地开发机可能只有 raw。
    """
    if LIVE_OHLCV_PATH.exists():
        return load_price_csv(LIVE_OHLCV_PATH), "live"
    print(
        f"  {LIVE_OHLCV_PATH} 不存在, 回退训练基准 {BASELINE_OHLCV_PATH} "
        f"(数据可能滞后! 生产环境应有 data/live/)"
    )
    return load_price_csv(BASELINE_OHLCV_PATH), "raw-fallback"


def _merge_older(base: pd.Series, older_src: pd.Series) -> pd.Series:
    """用 older_src 补 base 起点之前的旧史 (重叠段以 base 为准)。"""
    older = older_src[older_src.index < base.index.min()]
    if older.empty:
        return base
    combined = pd.concat([older, base]).sort_index()
    return combined[~combined.index.duplicated(keep="last")]


def fetch_coingecko_price() -> pd.Series:
    """拉 CoinGecko 全量日线收盘价 (约 2013 起)。失败抛异常。"""
    req = urllib.request.Request(COINGECKO_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    prices = data.get("prices") or []
    if not prices:
        raise ValueError("CoinGecko 返回空 prices")
    rows = {}
    for ts_ms, price in prices:
        d = dt.datetime.utcfromtimestamp(ts_ms / 1000).date()
        rows[d] = float(price)   # 同日多点时取最后一个 (日末)
    s = pd.Series(rows, name="close").astype(float)
    s.index.name = "date"
    return s.sort_index()


def build_price(use_coingecko: bool) -> pd.Series:
    """组装价格序列: live 为主 (拿最新) + raw 补旧史 (保住 live 起点前的周期底);
    --coingecko 时再用 CoinGecko 补更早旧史。重叠段一律以更新的源为准。"""
    price, src = load_live_price()
    # raw 补 live 起点 (约 2020) 之前的旧史 (2018-2020), 含一个周期底。
    # 回退模式下 base 已是 raw 本身, 跳过。
    if src == "live" and BASELINE_OHLCV_PATH.exists():
        price = _merge_older(price, load_price_csv(BASELINE_OHLCV_PATH))
    if use_coingecko:
        price = _merge_older(price, fetch_coingecko_price())
    return price


def compute_ahr999(price: pd.Series) -> pd.Series:
    """按原始公式算 ahr999 序列 (前 199 天因不足 200 日窗口为 NaN, 已丢弃)。"""
    log_price = np.log(price)
    # 200 日几何均值 = exp(200日 ln 均值)
    dca_cost = np.exp(log_price.rolling(DCA_WINDOW, min_periods=DCA_WINDOW).mean())

    coin_days = pd.Series(
        [(d - GENESIS).days for d in price.index], index=price.index, dtype=float
    )
    exp_valuation = 10 ** (EXP_A * np.log10(coin_days) + EXP_B)

    ahr = (price / dca_cost) * (price / exp_valuation)
    return ahr.dropna()


def classify(v: float) -> str:
    if v < 0.45:
        return "抄底区"
    if v < 1.2:
        return "定投区"
    if v < 5:
        return "观望区"
    return "泡沫区"


def atomic_write(series: pd.Series, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = series.rename("value").to_frame()
    out.index.name = "date"
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=".ahr999_", suffix=".tmp", delete=False
    ) as tmp:
        out.to_csv(tmp.name)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def main() -> None:
    ap = argparse.ArgumentParser(description="计算 ahr999 定投指数全历史序列")
    ap.add_argument("--coingecko", action="store_true",
                    help="先拉 CoinGecko 全量日线补旧史 (约2013起), 序列更长")
    ap.add_argument("--dry-run", action="store_true",
                    help="只算不写, 打印尾部 + 当前区间")
    args = ap.parse_args()

    price = build_price(args.coingecko)
    ahr = compute_ahr999(price)
    if ahr.empty:
        raise SystemExit("ahr999 计算结果为空 (价格历史不足 200 天?)")

    last_date = ahr.index[-1]
    last_val = float(ahr.iloc[-1])
    print(f"价格区间: {price.index[0]} -> {price.index[-1]}  ({len(price)} 天)")
    print(f"ahr999 : {ahr.index[0]} -> {last_date}  ({len(ahr)} 天)")
    print(f"当前 ahr999 = {last_val:.4f}  [{classify(last_val)}]")
    print("分位参考: <0.45 抄底 | 0.45-1.2 定投 | 1.2-5 观望 | >=5 泡沫")

    if args.dry_run:
        print("\n[dry-run] 未写文件。尾部 5 行:")
        print(ahr.tail().round(4).to_string())
        return

    atomic_write(ahr, OUTPUT_CSV)
    print(f"\n已写入: {OUTPUT_CSV}  ({len(ahr)} 行)")


if __name__ == "__main__":
    main()
