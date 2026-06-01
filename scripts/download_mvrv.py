#!/usr/bin/env python3
"""
BTC MVRV 下载器（BGeometrics 正确版，适配返回纯列表）
输出：data/external/mvrv_btc.csv（date, mv, rv, mvrv）
"""
from __future__ import annotations
import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = PROJECT_ROOT / "data" / "external" / "mvrv_btc.csv"

# ↓↓↓ 替换成你自己的完整 Token ↓↓↓
API_TOKEN = "CO1aw4vcz1"

BASE_URL = "https://api.bgeometrics.com/v1"
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}

# 正确 endpoint
METRICS = {
    "mvrv": "mvrv",
    "mv": "market_cap",
    "rv": "realized_cap"
}

def fetch_metric(metric_name: str, start: str, end: str) -> pd.DataFrame:
    url = f"{BASE_URL}/{metric_name}"
    params = {"start": start, "end": end, "interval": "1d"}
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=60)
            r.raise_for_status()
            # BGeometrics 直接返回列表，不是 {"data": [...]}
            data = r.json()
            # 加个保护：如果是 dict 才取 data（防止以后改格式）
            if isinstance(data, dict) and "data" in data:
                data = data["data"]
            df = pd.DataFrame(data)
            # t=时间戳(秒), v=数值
            df["date"] = pd.to_datetime(df["t"], unit="s").dt.date
            df = df.rename(columns={"v": metric_name})
            df = df.drop(columns=["t"]).set_index("date")
            return df
        except Exception as e:
            wait = 2 ** attempt
            print(f"⚠️ {metric_name} 失败({attempt+1}/3): {e} — {wait}s 重试")
            time.sleep(wait)
    sys.exit(f"❌ {metric_name} 连续失败")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    dfs = []
    for name, endpoint in METRICS.items():
        print(f"📡 拉取 {name} ({endpoint}) ...")
        df = fetch_metric(endpoint, args.start, args.end)
        dfs.append(df)

    df = pd.concat(dfs, axis=1).sort_index()
    df = df.rename(columns={
        "market_cap": "mv",
        "realized_cap": "rv"
    })
    # 自己算一遍 mvrv（稳妥）
    df["mvrv"] = df["mv"] / df["rv"]
    df = df.dropna(subset=["mv", "rv", "mvrv"])

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out)
    print("\n✅ 已保存", out)
    print(f"   区间: {df.index.min()} ~ {df.index.max()}, 行数: {len(df)}")
    print(f"   MVRV: {df['mvrv'].min():.2f} ~ {df['mvrv'].max():.2f}")

if __name__ == "__main__":
    sys.exit(main())