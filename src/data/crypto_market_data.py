"""crypto-market-data 适配器 — 读其 JSON, 转成 dashboard 用的 CSV.

数据源: https://github.com/ErcinDedeoglu/crypto-market-data (CC BY 4.0)。
**署名强制** (见市场页底部)。GitHub 托管, 不被 Binance 451 地域封锁。

为什么用它: 本机/VPS 所在地区被 Binance 期货 fapi 451 封锁, 拿不到
funding/OI/多空比。该仓库提供全市场聚合 (CryptoQuant 口径) 的日频长历史
(2022-12 起), 经 GitHub Actions 每日更新, VPS 只需 git pull 即新鲜。

口径提醒 (与 Binance 不同, 故写入独立的 cmd_*.csv, 不污染研究基准):
  - funding: 全市场聚合 (符号/尺度可能与币安单家相反), Decimal(%)。
  - open_interest: 全市场 OI (USD), 约为币安单家的数倍。
  - taker_buy_sell_ratio: taker 买卖比, **不是**多空账户比, 市场页据实标注。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"

# (源 JSON, 输出 CSV, 值列名) — 单一注册表, 加源只改这里 (DRY)
DATASETS: dict[str, tuple[str, str, str]] = {
    "funding": ("btc_funding_rates.json", "cmd_funding.csv", "funding_rate_mean"),
    "open_interest": ("btc_open_interest.json", "cmd_open_interest.csv", "open_interest_usd"),
    "taker_ratio": ("btc_taker_buy_sell_ratio.json", "cmd_taker_ratio.csv", "taker_buy_sell_ratio"),
}


def repo_dir() -> Path:
    """crypto-market-data 仓库位置 — 默认与 FcstLabPro 同级, 可用 env 覆盖。"""
    env = os.getenv("CRYPTO_MARKET_DATA_DIR", "").strip()
    return Path(env) if env else PROJECT_ROOT.parent / "crypto-market-data"


def _json_to_df(path: Path, value_col: str) -> pd.DataFrame:
    """JSON {data:[{timestamp,value}]} → date 索引的单列 df。"""
    payload = json.loads(path.read_text())
    rows = payload.get("data", []) or []
    if not rows:
        return pd.DataFrame(columns=[value_col], index=pd.DatetimeIndex([], name="date"))
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms").dt.normalize()
    df = df[["date", "value"]].rename(columns={"value": value_col})
    df = df.dropna().drop_duplicates("date", keep="last").sort_values("date")
    return df.set_index("date")


def convert_one(key: str) -> pd.DataFrame:
    """转换单个数据集 → 写 data/external/cmd_*.csv, 返回 date 索引 df (空=无数据)。"""
    src_name, out_name, value_col = DATASETS[key]
    src = repo_dir() / "data" / "daily" / src_name
    if not src.exists():
        raise FileNotFoundError(
            f"找不到 {src} — crypto-market-data 是否已 clone 到与 FcstLabPro 同级? "
            "(或设 CRYPTO_MARKET_DATA_DIR 指向其位置)"
        )
    df = _json_to_df(src, value_col)
    if not df.empty:
        EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(EXTERNAL_DIR / out_name)
    return df
