#!/usr/bin/env python3
"""
audit_bgeo_nan.py — BGeo 候选指标在 2020-2025 基准内的 NaN 体检.

依赖文档: docs/plans/phase2.5_feature_landscape_v0601.md §2.2 + §5.2
依赖原因: review 文档指出 L0/L1/L2 分级是"假设而非验证",
          需要每个指标在实际 BTC 基准日历内做 NaN 体检后才能正确分级.

用法:
    python scripts/audit_bgeo_nan.py
    python scripts/audit_bgeo_nan.py --bgeo /path/to/files --out path/to/audit.json

输出:
    - 控制台: 每指标的 NaN 状况表 + L0/L1/L2/L3 自动分级
    - JSON: data/external/onchain/nan_audit.json (持久化, 可被 sub config 引用)

NaN 体检维度 (每个指标):
    - data_start / data_end:        指标自身数据范围
    - rows_in_baseline:             与 BTC 2020-2025 日历 align 后的有效行数
    - rows_total_baseline:          BTC 基准总行数 (2192, 含周末因为 BTC 7×24)
    - coverage:                     rows_in_baseline / rows_total_baseline
    - nan_count:                    align 后 NaN 个数
    - leading_nulls:                BGeo 数据开头连续 [ts, None] 段长度
    - leading_nulls_after_2020:     2020-01-01 之后的前导 NaN 段长度 (重点)
    - level:                        自动判定 L0/L1/L2/L3 (按 phase2.5 §2.2 规则)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

# ====== 候选指标清单 (与 phase2.5_feature_landscape_v0601.md §4.2 5 个 sub 对应) ======
CANDIDATES: dict[str, list[str]] = {
    "E19-PUELL": [
        "puell_multiple_data",
    ],
    "E19-MINER": [
        "miner_balance",
        "miner_out_flows",
        "miner_reserves",
        "miner_sell_presure",
    ],
    "E19-MVRV-EXT": [
        "mvrv_data",
        "mvrv_365dma",
        "mvrv_diff",
        "mvrv_zscore_data",
        "mvrv_zscore_adapt_data",
    ],
    "E19-STABLE": [
        "stablecoin_supply",
        "stablecoin_usdt",
        "stablecoin_dai",
        "stablecoin_pax",
        "stablecoin_others",
    ],
}

# ====== 基准日历 (锁定, lesson_0601) ======
BASELINE_START = "2020-01-01"
BASELINE_END = "2025-12-31"

DEFAULT_BGEO = Path("/home/jupyter/qiu/github/bgeometrics.github.io/files")


def load_bgeo_series(json_path: Path) -> pd.Series | None:
    """加载 BGeo list-of-pairs JSON 为 pd.Series (index=date, value=float).

    返回 None 表示 schema 不支持 / parse 失败.
    """
    try:
        with open(json_path) as f:
            data = json.load(f)
        if not isinstance(data, list) or not data:
            return None
        if not isinstance(data[0], list) or len(data[0]) < 2:
            return None

        ts_list, val_list = [], []
        for row in data:
            if not isinstance(row, list) or len(row) < 2:
                continue
            ts_list.append(row[0])
            val_list.append(row[1])  # None 也保留

        s = pd.Series(
            val_list,
            index=pd.to_datetime(ts_list, unit="ms"),
            name=json_path.stem,
        )
        # 去重 (同一日多条取最后)
        s = s[~s.index.duplicated(keep="last")].sort_index()
        return s
    except Exception as e:
        print(f"  ❌ {json_path.name}: parse 失败 {e}", file=sys.stderr)
        return None


def count_leading_nulls(s: pd.Series, after: date | None = None) -> int:
    """统计 Series 开头连续 NaN 数. 可选: 仅统计 `after` 之后的."""
    if after is not None:
        s = s[s.index >= pd.to_datetime(after)]
    if len(s) == 0:
        return 0
    nan_mask = s.isna().values
    if not nan_mask[0]:
        return 0
    # 找第一个非 NaN 位置
    for i, v in enumerate(nan_mask):
        if not v:
            return i
    return len(s)


def classify_level(coverage: float, leading_after: int, data_start: date) -> str:
    """按 phase2.5 §2.2 规则自动分级.

    L0: 覆盖率 100% 且 2020 后无前导 NaN
    L1: 覆盖率 ≥ 70%
    L2: 覆盖率 < 70%
    L3: 数据已停 (last_data < 2025)
    """
    if coverage == 1.0 and leading_after == 0:
        return "L0"
    if coverage >= 0.70:
        return "L1"
    return "L2"


def audit_indicator(name: str, bgeo_dir: Path, baseline_index: pd.DatetimeIndex) -> dict:
    """单指标体检."""
    json_path = bgeo_dir / f"{name}.json"
    if not json_path.exists():
        return {
            "name": name,
            "error": "file_not_found",
            "path": str(json_path),
        }

    s = load_bgeo_series(json_path)
    if s is None or len(s) == 0:
        return {"name": name, "error": "parse_failed_or_empty"}

    # 与 BTC 基准日历 align
    aligned = s.reindex(baseline_index)

    data_start = s.index.min().date()
    data_end = s.index.max().date()
    rows_in_baseline = int(aligned.notna().sum())
    rows_total = len(baseline_index)
    coverage = rows_in_baseline / rows_total
    nan_count = int(aligned.isna().sum())
    leading_total = count_leading_nulls(s)
    leading_after = count_leading_nulls(aligned)

    # L3: 数据停更
    days_stale = (date.today() - data_end).days
    if days_stale > 90:
        level = "L3"
    else:
        level = classify_level(coverage, leading_after, data_start)

    return {
        "name": name,
        "data_start": str(data_start),
        "data_end": str(data_end),
        "days_stale": days_stale,
        "raw_rows": len(s),
        "rows_in_baseline": rows_in_baseline,
        "rows_total_baseline": rows_total,
        "coverage_pct": round(coverage * 100, 2),
        "nan_count_aligned": nan_count,
        "leading_nulls_raw": leading_total,
        "leading_nulls_after_2020": leading_after,
        "level": level,
    }


def print_audit_table(results: dict[str, list[dict]]) -> None:
    """漂亮打印 audit 结果."""
    print("\n" + "═" * 100)
    print(f"BGeo NaN Audit (基准: {BASELINE_START} ~ {BASELINE_END})")
    print("═" * 100)

    headers = [
        "指标", "data_start", "data_end", "coverage", "NaN", "lead_2020+", "stale_d", "level"
    ]
    fmt = "  {:<28} {:<12} {:<12} {:>8} {:>5} {:>10} {:>7} {:>5}"

    for sub_name, items in results.items():
        print(f"\n[{sub_name}]")
        print(fmt.format(*headers))
        print("  " + "─" * 96)
        for r in items:
            if "error" in r:
                print(f"  {r['name']:<28} ❌ {r['error']}")
                continue
            print(fmt.format(
                r["name"][:28],
                r["data_start"],
                r["data_end"],
                f"{r['coverage_pct']:.1f}%",
                r["nan_count_aligned"],
                r["leading_nulls_after_2020"],
                r["days_stale"],
                r["level"],
            ))

    # 等级分布汇总
    print("\n" + "─" * 100)
    print("等级分布:")
    all_items = [r for items in results.values() for r in items if "error" not in r]
    by_level = {}
    for r in all_items:
        by_level.setdefault(r["level"], []).append(r["name"])
    for lv in ["L0", "L1", "L2", "L3"]:
        names = by_level.get(lv, [])
        print(f"  {lv}: {len(names)} 个  {names if names else ''}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bgeo", type=Path, default=DEFAULT_BGEO,
                    help=f"BGeo files 目录 (默认: {DEFAULT_BGEO})")
    ap.add_argument("--btc-csv", type=Path,
                    default=Path("data/raw/btc_binance_BTCUSDT_1d.csv"),
                    help="BTC csv (用于获取基准日历)")
    ap.add_argument("--out", type=Path,
                    default=Path("data/external/onchain/nan_audit.json"),
                    help="输出 audit JSON 路径")
    args = ap.parse_args()

    if not args.bgeo.exists():
        print(f"❌ BGeo 目录不存在: {args.bgeo}", file=sys.stderr)
        return 1
    if not args.btc_csv.exists():
        print(f"❌ BTC csv 不存在: {args.btc_csv}", file=sys.stderr)
        return 1

    # 构建基准日历 (用 BTC csv 实际日期, 不是 date_range, 因为可能跳过停盘日)
    btc = pd.read_csv(args.btc_csv, parse_dates=[0], index_col=0)
    baseline_idx = btc.index[
        (btc.index >= pd.to_datetime(BASELINE_START))
        & (btc.index <= pd.to_datetime(BASELINE_END))
    ]
    print(f"✅ BTC 基准日历: {len(baseline_idx)} 行 ({baseline_idx[0].date()} ~ {baseline_idx[-1].date()})")

    # 逐 sub 逐指标体检
    results: dict[str, list[dict]] = {}
    for sub_name, indicators in CANDIDATES.items():
        results[sub_name] = []
        for ind in indicators:
            r = audit_indicator(ind, args.bgeo, baseline_idx)
            results[sub_name].append(r)

    # 打印
    print_audit_table(results)

    # 持久化
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out_data = {
        "baseline_start": BASELINE_START,
        "baseline_end": BASELINE_END,
        "baseline_rows": len(baseline_idx),
        "audit_date": str(date.today()),
        "bgeo_dir": str(args.bgeo),
        "results": results,
    }
    with open(args.out, "w") as f:
        json.dump(out_data, f, indent=2, ensure_ascii=False)
    print(f"\n✅ 已保存: {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
