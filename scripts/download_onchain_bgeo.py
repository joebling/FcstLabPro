#!/usr/bin/env python3
"""下载 BGeometrics 链上指标 JSON → CSV.

数据源: https://charts.bgeometrics.com/files/{indicator}.json
落地:   data/external/onchain/{indicator}.csv  (schema: date,value)

特性:
  - 原子写入 (临时文件 + rename), 不破坏现有缓存
  - 健康检查 (status, size, sha256, freshness) 写入 healthcheck.json
  - 支持自定义 indicator 子集
  - 兼容两种 JSON 格式: list-of-pairs 和 dict-of-columns

参考: docs/plans/onchain_lth_sth_feature_plan.md §5
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd
# requests 在 fetch_one() 里 lazy import, 避免 parser 单元测试也强制依赖

# ─────────────────────────────────────────────────────────────
# 配置: 11 个 indicator (6 核心 LTH/STH + 5 候选)
# ─────────────────────────────────────────────────────────────
CORE_INDICATORS = [
    "lth_mvrv", "sth_mvrv",
    "lth_nupl", "sth_nupl",
    "lth_sopr", "sth_sopr",
]

CANDIDATE_INDICATORS = [
    "aviv",
    "reserve_risk",
    "mvrv_data",
    "mvrv_zscore_data",
    "nupl_data",
]

ALL_INDICATORS = CORE_INDICATORS + CANDIDATE_INDICATORS

BASE_URL = "https://charts.bgeometrics.com/files/{name}.json"
DEFAULT_CACHE_DIR = Path("data/external/onchain")
HTTP_TIMEOUT = 30
USER_AGENT = "FcstLabPro/0.1 (research; bgeometrics CDN client)"


# ─────────────────────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────────────────────
@dataclass
class FetchResult:
    indicator: str
    status: str           # "ok" | "http_error" | "parse_error" | "empty"
    http_code: int | None
    bytes_downloaded: int
    rows: int
    first_date: str | None
    last_date: str | None
    sha256: str | None
    last_modified: str | None
    error: str | None
    saved_to: str | None


# ─────────────────────────────────────────────────────────────
# JSON parser: 处理两种格式
# ─────────────────────────────────────────────────────────────
def parse_payload(raw: Any) -> pd.DataFrame:
    """两种格式都支持:
       1) list of [ts_ms, value]  ← 绝大多数 BGeo 文件
       2) dict {"d": {idx: ts}, "<col>": {idx: val}}  ← _all 系列
    """
    if isinstance(raw, list):
        if not raw:
            raise ValueError("empty list payload")
        first = raw[0]
        if isinstance(first, list) and len(first) >= 2:
            df = pd.DataFrame(raw, columns=["ts_ms", "value"] + [f"extra_{i}" for i in range(len(first) - 2)])
            df = df[["ts_ms", "value"]]
        elif isinstance(first, dict):
            df = pd.DataFrame(raw)
            # 推测时间列与数值列
            ts_col = next((c for c in df.columns if c.lower() in ("ts", "timestamp", "d", "date")), df.columns[0])
            val_col = next((c for c in df.columns if c != ts_col), df.columns[-1])
            df = df.rename(columns={ts_col: "ts_ms", val_col: "value"})[["ts_ms", "value"]]
        else:
            raise ValueError(f"unrecognized list element type: {type(first)}")
    elif isinstance(raw, dict):
        df = pd.DataFrame(raw)
        # _all 类型: 多列, 第一列是时间, 其他列任选第一个数值列
        cols = list(df.columns)
        ts_col = cols[0]
        val_col = next((c for c in cols[1:] if pd.api.types.is_numeric_dtype(df[c])), cols[-1])
        df = df.rename(columns={ts_col: "ts_ms", val_col: "value"})[["ts_ms", "value"]]
    else:
        raise ValueError(f"unrecognized top-level type: {type(raw)}")

    df["date"] = pd.to_datetime(df["ts_ms"], unit="ms").dt.normalize()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"]).drop_duplicates("date").sort_values("date")
    return df[["date", "value"]].reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
# 下载 + 原子写入
# ─────────────────────────────────────────────────────────────
def fetch_one(indicator: str, cache_dir: Path, dry_run: bool = False) -> FetchResult:
    import requests  # lazy import
    url = BASE_URL.format(name=indicator)
    out_path = cache_dir / f"{indicator}.csv"

    try:
        resp = requests.get(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as e:
        return FetchResult(indicator, "http_error", None, 0, 0, None, None, None, None, str(e), None)

    if resp.status_code != 200:
        return FetchResult(indicator, "http_error", resp.status_code, len(resp.content),
                           0, None, None, None, resp.headers.get("Last-Modified"),
                           f"HTTP {resp.status_code}", None)

    raw_bytes = resp.content
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    last_modified = resp.headers.get("Last-Modified")

    try:
        payload = resp.json()
        df = parse_payload(payload)
    except (json.JSONDecodeError, ValueError) as e:
        return FetchResult(indicator, "parse_error", 200, len(raw_bytes), 0, None, None,
                           sha256, last_modified, str(e), None)

    if df.empty:
        return FetchResult(indicator, "empty", 200, len(raw_bytes), 0, None, None,
                           sha256, last_modified, "parsed df is empty", None)

    first_date = df["date"].iloc[0].date().isoformat()
    last_date = df["date"].iloc[-1].date().isoformat()

    if dry_run:
        return FetchResult(indicator, "ok", 200, len(raw_bytes), len(df),
                           first_date, last_date, sha256, last_modified, None, "(dry-run)")

    # 原子写入: tmp 文件 + rename
    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=cache_dir, suffix=".tmp", delete=False) as tmp:
        df.to_csv(tmp.name, index=False)
        tmp_path = Path(tmp.name)
    tmp_path.replace(out_path)

    return FetchResult(indicator, "ok", 200, len(raw_bytes), len(df),
                       first_date, last_date, sha256, last_modified, None, str(out_path))


# ─────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--indicators", nargs="+", default=None,
                    help="子集 (默认全部 11 个). 例: --indicators lth_mvrv sth_mvrv")
    ap.add_argument("--core-only", action="store_true", help="只下 6 个核心 LTH/STH")
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    ap.add_argument("--dry-run", action="store_true", help="只 fetch + parse, 不落盘")
    args = ap.parse_args()

    if args.core_only:
        indicators = CORE_INDICATORS
    elif args.indicators:
        indicators = args.indicators
    else:
        indicators = ALL_INDICATORS

    print(f"📡 下载 {len(indicators)} 个 indicator 到 {args.cache_dir} (dry_run={args.dry_run})")
    print("─" * 90)

    results: list[FetchResult] = []
    for ind in indicators:
        print(f"  {ind:<22} ... ", end="", flush=True)
        r = fetch_one(ind, args.cache_dir, dry_run=args.dry_run)
        results.append(r)
        if r.status == "ok":
            print(f"✅ {r.rows:>5} 行  {r.first_date} → {r.last_date}  ({r.bytes_downloaded // 1024} KB)")
        else:
            print(f"❌ {r.status}: {r.error}")

    # 健康检查报告
    if not args.dry_run:
        args.cache_dir.mkdir(parents=True, exist_ok=True)
        health_path = args.cache_dir / "healthcheck.json"
        health = {
            "downloaded_at": dt.datetime.utcnow().isoformat() + "Z",
            "n_total": len(results),
            "n_ok": sum(1 for r in results if r.status == "ok"),
            "results": [asdict(r) for r in results],
        }
        with open(health_path, "w") as f:
            json.dump(health, f, indent=2, default=str)
        print(f"\n📋 healthcheck → {health_path}")

    n_ok = sum(1 for r in results if r.status == "ok")
    n_fail = len(results) - n_ok
    print(f"\n{'═' * 90}")
    print(f"完成: {n_ok}/{len(results)} 成功, {n_fail} 失败")
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
