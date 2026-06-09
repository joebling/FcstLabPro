"""Rolling vs Expanding 分位深度审计.

输出 4 张关键表 (写进 docs/plans/rolling_vs_expanding_audit_20260609.md):
A. 各指标在历史 4 个周期顶/底的分位对比 (expanding vs rolling 2y)
B. RR 周期衰减表 (已有, 补充更精确)
C. 全 19 指标当前快照 (2026-06-01) 两口径对比
D. 命中率: 阈值 ≥85 (顶) / ≤15 (底) 在历史顶/底实际触发情况

数据由调用方写入 markdown.
"""
import sys
sys.path.insert(0, '.')
import pandas as pd
import numpy as np
from pathlib import Path

# 复用 INDICATORS 定义
from scripts.research.topping_indicator_ic import INDICATORS, DATA

ROLL_WIN = 730  # 2 年
MIN_PERIODS = 180

# 历史周期顶/底锚点 (用户提供 + 实证验证)
TOPS = [
    ('2017-12-16', '2017-2018'),
    ('2021-04-13', '2021-04 局部顶'),
    ('2021-11-08', '2021-11 真顶'),
    ('2025-10-06', '2025-10 真顶'),
]
BOTTOMS = [
    ('2018-12-15', '2018-12 大底'),
    ('2020-03-12', '2020-03 COVID 底'),
    ('2022-11-21', '2022-11 Luna 后底'),
]

# 加载价格
price = pd.read_csv(DATA / 'raw/btc_binance_BTCUSDT_1d.csv',
                    parse_dates=['date']).set_index('date')['close']

def load_series(rel_path, col):
    p = DATA / rel_path
    if not p.exists():
        return None
    df = pd.read_csv(p, parse_dates=['date'])
    return df.set_index('date')[col].sort_index().dropna()

def pct_exp(s):
    # 矢量化: pandas expanding rank (pct=True) 返回 [0,1]
    return s.expanding(min_periods=1).rank(pct=True) * 100

def pct_roll(s, win=ROLL_WIN):
    # 矢量化 rolling rank (pct=True) 返回 [0,1]
    return s.rolling(window=win, min_periods=MIN_PERIODS).rank(pct=True) * 100

# 加载全部指标
print("# 加载指标...")
series_dict = {}
for name, (path, col, direction) in INDICATORS.items():
    s = load_series(path, col)
    if s is None or len(s) < 365:
        print(f"  跳过 {name}: 数据缺失或不足")
        continue
    series_dict[name] = (s, direction)
print(f"# 加载完成: {len(series_dict)} 个指标\n")

# === 表 A: 历史顶/底锚点分位对比 ===
print("="*120)
print("表 A: 历史周期顶/底锚点 — Expanding vs Rolling-2y 分位对比")
print("="*120)
print(f"\n顶部锚点 (理想触发条件: 分位 ≥85%)")
print(f"{'指标':<22}", end='')
for date_str, label in TOPS:
    print(f"{label:^24}", end='')
print()
print(f"{'':22}", end='')
for date_str, label in TOPS:
    print(f"{'exp / roll2y':^24}", end='')
print()
print("-"*22 + "-"*(24*len(TOPS)))
top_table = []
for name, (s, direction) in series_dict.items():
    if direction != -1:  # 只看反向指标 (高=贵)
        continue
    pe = pct_exp(s); pr = pct_roll(s)
    row = [name]
    print(f"{name:<22}", end='')
    for date_str, label in TOPS:
        d = pd.Timestamp(date_str)
        if d in pe.index:
            ev = pe.loc[d]; rv = pr.loc[d]
            ev_str = f"{ev:5.1f}%" if pd.notna(ev) else "  NaN"
            rv_str = f"{rv:5.1f}%" if pd.notna(rv) else "  NaN"
            # 加标记: rolling 触发 ≥85 → 
            mark = '' if pd.notna(rv) and rv>=85 else ' '
            print(f"  {ev_str} / {rv_str} {mark}    ", end='')
            row.append((ev, rv))
        else:
            print(f"   N/A         ", end='')
            row.append((None, None))
    print()
    top_table.append(row)

print(f"\n底部锚点 (理想触发条件: 分位 ≤15%)")
print(f"{'指标':<22}", end='')
for date_str, label in BOTTOMS:
    print(f"{label:^24}", end='')
print()
print("-"*22 + "-"*(24*len(BOTTOMS)))
bot_table = []
for name, (s, direction) in series_dict.items():
    pe = pct_exp(s); pr = pct_roll(s)
    row = [name]
    print(f"{name:<22}", end='')
    for date_str, label in BOTTOMS:
        d = pd.Timestamp(date_str)
        if d in pe.index:
            ev = pe.loc[d]; rv = pr.loc[d]
            ev_str = f"{ev:5.1f}%" if pd.notna(ev) else "  NaN"
            rv_str = f"{rv:5.1f}%" if pd.notna(rv) else "  NaN"
            mark = '' if pd.notna(rv) and rv<=15 else ' '
            print(f"  {ev_str} / {rv_str} {mark}    ", end='')
            row.append((ev, rv))
        else:
            print(f"   N/A         ", end='')
            row.append((None, None))
    print()
    bot_table.append(row)

# === 表 C: 当前快照 (2026-06-01) ===
print("\n" + "="*120)
print("表 C: 当前快照 (2026-06-01) — 两种口径对比")
print("="*120)
print(f"{'指标':<22}{'方向':>6}{'最新值':>12}{'expanding分位':>15}{'rolling-2y分位':>17}{'差异':>10}")
print("-"*82)
snap_date = pd.Timestamp('2026-06-01')
snap_rows = []
for name, (s, direction) in series_dict.items():
    if snap_date not in s.index:
        # 用 asof
        v = s.asof(snap_date)
        if pd.isna(v): continue
    else:
        v = s.loc[snap_date]
    pe = pct_exp(s); pr = pct_roll(s)
    ev = pe.asof(snap_date); rv = pr.asof(snap_date)
    diff = rv - ev if pd.notna(rv) and pd.notna(ev) else None
    dir_str = '高=贵' if direction==-1 else '高=便宜'
    print(f"{name:<22}{dir_str:>6}{v:>12.4f}{ev:>14.1f}%{rv:>16.1f}%{(diff if diff else 0):>+9.1f}")
    snap_rows.append((name, direction, v, ev, rv, diff))

# === 表 D: 全周期触发频率 (rolling vs expanding) ===
print("\n" + "="*120)
print("表 D: 各指标历史触发频率对比 (≥85 顶部 / ≤15 底部)")
print("="*120)
print(f"{'指标':<22}{'≥85天 (exp)':>14}{'≥85天 (roll2y)':>17}{'≤15天 (exp)':>14}{'≤15天 (roll2y)':>17}")
print("-"*84)
trig_rows = []
for name, (s, direction) in series_dict.items():
    pe = pct_exp(s); pr = pct_roll(s)
    n_high_e = (pe>=85).sum(); n_high_r = (pr>=85).sum()
    n_low_e = (pe<=15).sum(); n_low_r = (pr<=15).sum()
    print(f"{name:<22}{n_high_e:>14}{n_high_r:>17}{n_low_e:>14}{n_low_r:>17}")
    trig_rows.append((name, direction, n_high_e, n_high_r, n_low_e, n_low_r))

# 导出数据到 csv 备用
out = Path('experiments/research/rolling_vs_expanding_audit.csv')
out.parent.mkdir(parents=True, exist_ok=True)
import json
dump = {
    'top_anchors': [(d, l) for d, l in TOPS],
    'bot_anchors': [(d, l) for d, l in BOTTOMS],
    'snapshot_2026_06_01': [
        {'name': n, 'direction': dr, 'value': float(v) if pd.notna(v) else None,
         'pct_exp': float(e) if pd.notna(e) else None,
         'pct_roll2y': float(r) if pd.notna(r) else None}
        for n, dr, v, e, r, _ in snap_rows
    ],
    'trigger_counts': [
        {'name': n, 'direction': dr, 'high_exp': int(he), 'high_roll': int(hr),
         'low_exp': int(le), 'low_roll': int(lr)}
        for n, dr, he, hr, le, lr in trig_rows
    ],
}
with open('experiments/research/rolling_vs_expanding_audit.json', 'w', encoding='utf-8') as f:
    json.dump(dump, f, ensure_ascii=False, indent=2, default=str)
print(f"\n# 数据已存: experiments/research/rolling_vs_expanding_audit.json")
