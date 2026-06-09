# Lesson Learned: live_signal `fetch_latest_data` 吞下 partial bar

> **日期**: 2026-06-09
> **作者**: sam (with Qiu)
> **触发场景**: Qiu 查 dashboard 实盘账本发现两个问题 — “交易价不像是当日收盘” + “regime 与体感不符”
> **影响范围**: 6/5-6/9 实盘 4 笔交易 (e20c + e8 各两笔), 其中 6/7 SELL 减少收益 ≋ 4.06%

---

## TL;DR (1 分钟版)

生产 cron 在 UTC 00:10 拉 Binance API. 此时当日 1d bar 才开 10 分钟,
Binance 返回的 partial bar 的 `close` 字段实际是**该时刻的 last price**,
不是真正 24h 收盘. 下游 `is_bear_market` 和 entry/exit 执行全部被错价污染:

| 环节 | 防护 | 状态 |
|---|---|---|
| `data_freshness` gate (stage 3) | partial bar | 有 — 看 stale_days, partial bar `stale=0` 会误判为“新鲜” — 但不崩 |
| `live_signal.fetch_latest_data` (stage 4) | partial bar | **没有** — `df["close"].iloc[-1]` 拿到早盘瞬时价 |

**这是 lesson_0602 “写端/读端不对称” bug 的变体**: stage 3 守门员能拦住假数据,
stage 4 走同一份数据却裸奔.

---

## 1. 事件时间线 (生产事故)

| UTC 时刻 | 事件 | 账本后果 |
|---|---|---|
| 6/5 00:10 | cron stage 3 halt (last_date=6/1, 落后 4 天) — 干净 fail | 无 |
| 6/5 某时刻 | Qiu 手动重跑 `run_daily_nodock.sh` 补救 | csv 末尾=6/5 partial (last=63186), 写 BUY @ 63186 |
| 6/6 00:10 | cron OK, csv 末尾=6/6 partial (last=61448.84), regime=-8.69% | HOLD |
| 6/7 00:10 | cron OK, csv 末尾=6/7 partial (last=60865.64, 早盘瞬时低点) | regime=-11.83% → **误跳 SELL @ 60865.64** |
| 6/7 当日闭合 | 真实 close=63332.01, 真实 63d=-8.26% | **未到 -10% 阈值, 不应平仓** — 少赚 4.06% |
| 6/8 00:10 | cron OK, csv 末尾=6/8 partial (last=63186, **与 6/5 巧合**) | regime=-8.23% → BUY @ 63186 |
| 6/9 00:10 | cron OK, csv 末尾=6/9 partial (last=63032.13) | regime=-12.36% → SELL @ 63032.13 (真触发) |

**最决定性证据** — 6/6 日志原句:
```
2026-06-06 00:10 [INFO] Regime: 63d 滚动收益 = -8.69% (threshold=-10%)
```
用 6/6 真实 close (60884.62) 算 ≋ -9.53%, 不等于日志的 -8.69%.
用日志里的 `价格=61448.84` 算: 61448.84 / 67300.42 - 1 = **-8.69%** ✅ 完全吃上.
→ 系统吃的 \"6/6 close\" = 61448.84 = UTC 00:10 那一刻的 last price, 非真实收盘.

---

## 2. 根因分析

### 2.1 Binance API 的 partial bar 语义陷阱

`GET /api/v3/klines?interval=1d` 返回的列表中, **末尾 bar 可能是当日未闭合的 partial bar**:
- `close` = 查询那一刻的 last trade price (不是 UTC 24:00 收盘)
- `high/low/volume` = 从 UTC 00:00 到查询时刻的累计 (不完整)

任何在未过完当日 UTC 时拉的数据都存在这个问题 — 不是 Binance 的 bug,
是 API 语义: “最新一根”可以是未闭合 (Trading View / TradingView Lightweight Charts 也同语义).

### 2.2 训推差异被“双防护”遮蔽

- **训练时**: `data/raw/btc...csv` 是锁死的历史数据, 永远不含 partial bar → 训练/回测看不到这个 bug.
- **生产推理时**: cron 在 UTC 00:10 拉 → 100% 遭遇 partial bar.

两路径的“谁有责任处理 partial bar”是隐含的“生产侧负责”, 但 `fetch_latest_data`
原始实现直接读 csv 末尾一行, 没有完成这个隐含职责.

### 2.3 防线对比 (与 lesson_0602 同构)

| 环节 | partial bar 防护 | 状态 |
|---|---|---|
| downloader `download_binance_klines` | 不该写未闭合 bar 到 csv | 无 — 原语义就是写 “拉到什么写什么” |
| `data_freshness` gate (stage 3) | stale_days 计算 | 部分 — partial bar 会让 stale=0 看起来“新鲜”, gate 不会报错, 但也不会抦截 |
| `live_signal.fetch_latest_data` (stage 4) | drop partial bar | **原本没有, 本 lesson 补上** |
| `is_bear_market` | regime 门阈 | 不能在这里补 — 它信任上游给的 series |
| `_apply_signal_to_state` BUY 分支 | entry_price 源头 | 同上, 上游错了它只能跳进去 |

这也是为什么修在 `fetch_latest_data` 末尾是​​**唯一正确**​​的点: 它是​​**所有推理**​​上游的唯一闸門.

---

## 3. 修复方案

### 3.1 代码 (commit `<filled-on-push>`)

`scripts/live_signal.py`:
- 新增 `drop_partial_bar(df, *, now_utc=None) -> pd.DataFrame`
  - 检测末尾是否 UTC 今日 (或未来, 防未来时钟偏差), 是则 drop
  - 仅有 partial bar 时 raise (拒绝在缺数据情况下出信号)
  - `now_utc` 可注入 — 生产走实际时钟, 测试锁时间
- `fetch_latest_data` 3 个返回点都调用 `drop_partial_bar` 后再返回
- docstring 写明 “**lesson_0609 强制保证**: 返回的 df 末尾必为完整 bar”

### 3.2 单测 `tests/test_partial_bar_drop.py` (7/7 通过)

| 用例 | 锁什么 |
|---|---|
| `test_drops_when_last_bar_is_today_utc` | 末尾 UTC 今日 → drop |
| `test_keeps_when_last_bar_is_yesterday` | 末尾 为昨日 → 保留 |
| `test_drops_future_bar_defensively` | 末尾未来日期 (异常) → drop |
| `test_raises_when_only_partial_bar` | 仅 1 行且是 partial → raise |
| `test_empty_df_returns_empty` | 空 df → 不报错 |
| `test_now_utc_default_uses_real_clock` | 不传 now_utc → 走实际时钟 |
| `test_replays_2026_06_07_incident` | 事故现场回放 → 修复后丢 6/7 留 6/6 |

---

## 4. 损害评估 (保守)

仅计本次事件 (6/5-6/9, 4 笔交易):

| 交易 | 账本记录 | 真实应该 | 损失 |
|---|---|---|---|
| 6/7 e20c SELL @ 60865.64 | 误触发熊市 | regime 未到阈值, 不应 SELL | **少赚 4.06%** (同日反弹到 63332) |
| 6/7 e8 SELL @ 60865.64 | 同上 | 同上 | 同上 |
| 6/8 BUY @ 63186.00 (两个模型) | early 手 | 本该 HOLD (未平仓) | 高买 0.16% (小) |
| 6/9 SELL @ 63032.13 | 真熊市 | 真触发, OK | 价格是 partial 但决策对 |

**不包含** "如果历史上有多少次 partial bar 误触发" — 待 followup 回放 30 天.

---

## 4.5 反事实回放: 修复后 6/5-6/10 cron 会怎么跳?

以下是用当时 VPS data/live 真实当日 close 重算 regime, 预测修复后 cron 行为:

| cron UTC 日 | 看到的 today (T-1) | today close | T-63 close | 63d 收益 | regime | 动作 |
|---|---|---:|---:|---:|---|---|
| 6/5  | 6/4 | 63885.99 | 4/2: 66901.99 | **-4.51%**  | 非熊 | 模型决定 |
| 6/6  | 6/5 | 61056.47 | 4/3: 66964.30 | **-8.82%**  | 非熊 | 模型决定 |
| 6/7  | 6/6 | 60884.62 | 4/4: 67300.42 | **-9.53%**  | 非熊 (差 0.47%) | 模型决定 |
| 6/8  | 6/7 | 63332.01 | 4/5: 69034.18 | **-8.26%**  | 非熊 | 模型决定 |
| 6/9  | 6/8 | 63085.99 | 4/6: 68853.66 | **-8.38%**  | 非熊 | 模型决定 |
| **6/10** | 6/9 | 63032.13 | 4/7: 71924.22 | **-12.36%** | **熊市** | **在仓 -> 强制平仓, 空仓 -> SILENT** |

### 与事故现状逐日对比

| cron 日 | 事故现状 | 修复后预期 |
|---|---|---|
| 6/5  | halt + 手动重跑 BUY @63186 | 不 halt, 模型决定 (regime 不拦) |
| 6/6  | HOLD | HOLD (一致) |
| 6/7  | **SELL @60865 (误触发熊)** | **HOLD** — 救回同日反弹 4.06% |
| 6/8  | BUY @63186 (事故重仓) | HOLD (仓还在, 本就没平) |
| 6/9  | SELL @63032 (真触发) | HOLD (此时看 6/8 close -8.38%, 未到阈值) |
| **6/10** | (未跑) | **SELL** (看 6/9 close -12.36%, 真触发) |

### 两个 caveat

1. **模型 BUY/SILENT 本地无法精确模拟** — 需要跑 e20c/e8 的 137 个特征推理. 但结论不变:
   只要 regime 不拦 (6/5-6/9 都不拦), 最多就是模型按它本该的逻辑决定 BUY/SILENT,
   不会出现 "被 regime 误触发" 的交易.

2. **cron 看到的 'today' 晚一天** — 修复后 trade history 里 `entry_date`/`exit_date` 会比事故
   晚 1 天 (UTC 视角). 这是语义正确: 执行价是 T-1 完整 close, "on which day" 标 T-1 才合理.
   dashboard 展示与账本逻辑都不需调整.

### 净效益

| 救回的损失 | 数额 |
|---|---|
| 6/7 e20c 误触发 SELL -> 漏掉当日反弹 | **~4.06%** |
| 6/7 e8 误触发 SELL -> 漏掉当日反弹 (仓位境况不同, 但同价位) | **~4.06%** |
| 6/8 BUY @63186 高 tick -> 6/10 强平 -> 多一次 -0.24% 无意义交易 | 省掉 |

**最大救回**: 6/7 那次 -4% 假平仓不再发生.

---

## 5. 部署 / VPS 同步

```bash
# 本地 (本 PR)
git checkout fix/partial-bar-drop
git push origin fix/partial-bar-drop
# (PR / merge to main)

# VPS
cd /root/FcstLabPro && git pull origin main
# 下一次 UTC 00:10 cron 跳过 partial bar, 用真实 T-1 close
# 验证: tail /opt/fcstlabpro/logs/daily_<明日>.log 会看到
#   "丢弃 partial bar (date=<今日>, UTC 今日尚未闭合)"
```

无需重启 service, 无需重训模型 — cron 下次跳才重读文件.

---

## 6. 后续 (未完成, 待 followup PR)

1. **重刯最近 30 天实盘** — 用真实当日 close 重算 regime, 看有多少笔 SELL/BUY 是 partial bar 误触发; PnL 差异账
2. **`data_freshness` gate 升级** — 推荐 stale_days 计算也跳过当日 partial bar, 避免假阅动 stale_days=0
3. **downloader 侧双保险** — `download_binance_klines` 可选参数 `drop_incomplete_bar=True`, 在写 csv 前就刪揉
4. **文档 §10.1 / 生产手册** — 明记 “cron 拉数据 ≠ 拉到的都是完整 bar”

---

## 7. 教训

1. **“最新一条”不等于“最新完整一条”** — 任何按时间卷的 K 线 API,
   默认要问“末尾是否闭合”, 不能默认 trust.

2. **训推对称原则变体** — 训练吃“历史都是完整 bar”, 生产吃“末尾可能 partial”,
   两者输入分布不同 → 生产必须在输入进推理前拉齐到训练分布 (drop partial).

3. **多防线不是代替品** — lesson_0602 学到 “stage 3 + stage 4 读同一个路径常量”,
   但 “同一路径” 不代替 “同样的数据语义检查”. partial bar 吃了这个虚假安全感.

4. **价格不对劲 → 先查“价格从哪里读的”** — 本事故 Qiu 首发零是 “账本价不是当日收盘”,
   这是最高价值的 anchor. 任何“model 表现不对”调查, 先查上游价格源头.

---

*本文档与 lesson_0601 / lesson_0602 同系列, 均为数据治理 (Layer 0) 红线事件.*
