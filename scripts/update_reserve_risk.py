#!/usr/bin/env python3
"""Reserve Risk 续命脚本 — 历史基底 + BGeo REST API 尾巴 (缩放拼接).

背景 (2026-06 事故):
  BGeometrics 的静态文件 charts.bgeometrics.com/files/reserve_risk.json
  从 2025-12-29 起 value 全为 null (上游 VOCDD/币天计算断供), 官网自己也读这个空文件。
  唯一仍在更新的源是 REST API: https://bitcoin-data.com/v1/reserve-risk
  但 API 只给 ~4 年滚动窗口, 且单位与静态文件差一个恒定 ~1.9 倍 (Spearman 0.978)。

方案:
  reserve_risk.csv = 历史基底 (reserve_risk_history.csv, 2012→2025-12-28, 静态文件有效段)
                   + API 尾巴 (基底末日之后) × 缩放因子 (锚定重叠段, 使接缝连续)

缩放因子 = 重叠段最近 WINDOW 天的 中位(基底/API) — 鲁棒, 抵消单日噪声。
分位 regime gate 只看排名, 量级缩放不影响判断; 缩放仅为接缝视觉连续 + 绝对值可用。

用法:
  python scripts/update_reserve_risk.py            # 拉 API, 拼接, 写 reserve_risk.csv
  python scripts/update_reserve_risk.py --dry-run  # 只算不写, 打印接缝诊断
"""
from __future__ import annotations

import argparse
import datetime as dt
import tempfile
from pathlib import Path

import pandas as pd

ONCHAIN_DIR = Path("data/external/onchain")
HISTORY_CSV = ONCHAIN_DIR / "reserve_risk_history.csv"   # 冻结基底 (防 4 年窗口丢史)
OUTPUT_CSV = ONCHAIN_DIR / "reserve_risk.csv"            # 生产文件 (dashboard 读这个)
API_URL = "https://bitcoin-data.com/v1/reserve-risk"
RESCALE_WINDOW_DAYS = 90   # 用重叠段最近 N 天算缩放因子
HTTP_TIMEOUT = 30
USER_AGENT = "FcstLabPro/0.1 (research; reserve-risk stitch)"


def load_history() -> pd.Series:
    if not HISTORY_CSV.exists():
        raise FileNotFoundError(
            f"缺历史基底 {HISTORY_CSV}. 先从静态文件有效段生成 (见脚本 docstring)。"
        )
    df = pd.read_csv(HISTORY_CSV, parse_dates=["date"]).set_index("date")["value"]
    return df.sort_index()


def fetch_api() -> pd.Series:
    import json
    import time
    import urllib.error
    import urllib.request
    req = urllib.request.Request(API_URL, headers={"User-Agent": USER_AGENT})
    last_err = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                payload = json.load(resp)
            break
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:           # 限流: 指数退避重试
                wait = 5 * (attempt + 1)
                print(f"  HTTP 429 限流, {wait}s 后重试 ({attempt + 1}/5)...")
                time.sleep(wait)
                continue
            raise
    else:
        raise RuntimeError(f"API 拉取失败 (多次 429): {last_err}")
    df = pd.DataFrame(payload)
    df["date"] = pd.to_datetime(df["d"]).dt.normalize()
    s = df.set_index("date")["reserveRisk"].astype(float).sort_index()
    return s[~s.index.duplicated(keep="last")]


def compute_rescale(history: pd.Series, api: pd.Series) -> tuple[float, dict]:
    """重叠段最近 WINDOW 天的 中位(history/api)。返回 (factor, 诊断)。"""
    common = history.index.intersection(api.index)
    if len(common) == 0:
        raise ValueError("历史基底与 API 无重叠日, 无法定标 (API 窗口可能已不覆盖基底末日)。")
    recent = common[common >= common.max() - pd.Timedelta(days=RESCALE_WINDOW_DAYS)]
    ratio = (history.loc[recent] / api.loc[recent]).replace([float("inf")], pd.NA).dropna()
    factor = float(ratio.median())
    diag = {
        "overlap_days": len(common),
        "window_days": len(recent),
        "factor": round(factor, 4),
        "ratio_cv": round(float(ratio.std() / ratio.mean()), 4) if len(ratio) > 1 else 0.0,
        "spearman": round(float(api.loc[common].rank().corr(history.loc[common].rank())), 4),
    }
    return factor, diag


def stitch(history: pd.Series, api: pd.Series, factor: float) -> pd.Series:
    splice = history.index.max()
    tail = api[api.index > splice] * factor
    combined = pd.concat([history, tail])
    return combined[~combined.index.duplicated(keep="last")].sort_index()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="只算不写, 打印接缝诊断")
    args = ap.parse_args()

    history = load_history()
    api = fetch_api()
    factor, diag = compute_rescale(history, api)
    combined = stitch(history, api, factor)

    splice = history.index.max()
    tail_n = int((api.index > splice).sum())
    print(f" 历史基底: {history.index.min().date()} → {splice.date()} ({len(history)} 行)")
    print(f" API:      {api.index.min().date()} → {api.index.max().date()} ({len(api)} 行)")
    print(f" 缩放因子: {diag['factor']} (近{diag['window_days']}天中位 | CV {diag['ratio_cv']} | Spearman {diag['spearman']})")
    print(f"   接缝连续性: 基底末 {history.loc[splice]:.6f} vs API末×k {api.loc[splice] * factor:.6f}")
    print(f" 追加尾巴: {tail_n} 天 → 新末日 {combined.index.max().date()} = {combined.iloc[-1]:.6f}")
    print(f" 合计: {len(combined)} 行")

    if args.dry_run:
        print("\n(dry-run, 未写盘)")
        return

    out_df = combined.rename("value").reset_index()
    out_df.columns = ["date", "value"]
    ONCHAIN_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=ONCHAIN_DIR, suffix=".tmp", delete=False) as tmp:
        out_df.to_csv(tmp.name, index=False)
        tmp_path = Path(tmp.name)
    tmp_path.replace(OUTPUT_CSV)
    print(f"\n 写入 {OUTPUT_CSV} (更新 {dt.datetime.now(dt.timezone.utc).isoformat()})")


if __name__ == "__main__":
    main()
