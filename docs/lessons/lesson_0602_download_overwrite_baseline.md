# Lesson Learned: VPS `--download` 覆盖训练基准 csv

> **日期**: 2026-06-02
> **作者**: sam (with Qiu)
> **触发场景**: VPS `git push` 的 `update data` commit (95de1bf) 把 `data/raw/btc_binance_BTCUSDT_1d.csv` 基准覆盖
> **影响范围**: 所有依赖 sha 锁定基准的训练/复现 (E1/E8/E20c/E21b) + Wave 3 E23 实验

---

## TL;DR (1 分钟版)

本地 pull VPS 推上来的 `update data` 时, 顺手做了 sha 校验, 发现 `btc_binance_BTCUSDT_1d.csv` 的 sha256 从锁定值 `004bf07...` 变成了 `201a090...`。

调查发现 VPS 上的实时下载流程 (production pipeline / `--download`) **直接把实时拉取的数据写进了 `data/raw/` 训练基准文件**:

| | 锁定基准 | VPS 覆盖版 |
|---|---|---|
| 行数 | 3075 | 2346 |
| 起点 | 2018-01-01 | 2020-01-01 |
| 末尾 | 2026-06-01 | 2026-06-02 |
| sha256 | `004bf07...` ✅ | `201a090...` 🔴 |

这是 **lesson_0601 的同类事故 (训练基准被静默改写), 不同诱因 (上次是回填历史, 这次是实时下载覆盖)**。

**根因多层叠加**:
1. **训练基准与实时数据共用一个文件路径** (`data/raw/btc_binance_BTCUSDT_1d.csv`)
2. **`download_binance_klines` 直接 `to_csv` 覆盖写, 无任何保护**
3. **loader 的 sha 校验只 WARN 不阻塞** (注释甚至写着"防御 lesson_0601", 结果 WARN 被日志淹没无人看)
4. **`data/raw/*.csv` 的 .gitignore 是注释掉的** → 被覆盖的基准能 commit + push 回来

---

## 1. 事件时间线

| 时刻 (2026-06-02) | 事件 |
|---|---|
| 06:15 | VPS push `update data` (95de1bf): 下载 SOPR 数据 + 覆盖 btc 基准 |
| ~ | 本地 `git pull`, fast-forward |
| ~ | pull 后立即做 sha 校验 → `201a090...` ≠ 锁定 `004bf07...` 🔴 |
| ~ | 诊断: 基准被覆盖 (3075→2346 行, 2018→2020 起点) |
| ~ | `git checkout 8398906 -- data/raw/btc...csv` 只还原基准, SOPR 数据保留 |
| ~ | E20c 复现守门: model sha `8e34812f...` bit-exact ✅, 复现链恢复 |
| ~ | commit `ba74978`: 还原基准 + 事故留痕 |
| ~ | 用户决定上 A+C+D 三件套根治 |

---

## 2. 根因分析

### 2.1 路径耦合 (最核心)

`data/raw/btc_binance_BTCUSDT_1d.csv` 同时承担两个矛盾的角色:
- **训练基准**: 必须不可变, sha 锁定, 才能 bit-exact 复现
- **实时数据落点**: production pipeline `_stage_download_ohlcv` 把它当下载目标

每次 VPS 跑生产信号 (`--download`), 基准就被实时数据覆盖一次。

### 2.2 防线全失守

| 防线 | 应有作用 | 实际状态 (事故时) |
|---|---|---|
| downloader 写盘 | 不该覆盖基准 | 无保护, 直接 `to_csv` 覆盖 |
| loader sha 校验 | 不符应阻塞 | 只 `logger.warning`, 照跑 |
| .gitignore | 实时数据不进 git | `data/raw/*.csv` 忽略被注释掉 |

---

## 3. 修复方案 (A + C + D)

### A. 路径隔离 (治本)

- `data/raw/` = **不可变训练基准**, sha 锁定, 只读
- `data/live/` = **实时下载落点**, 可变, 进 .gitignore
- `download_binance_klines` 加 `_guard_raw_overwrite`: 写 `data/raw/` 下已存在文件时 raise (除非 `allow_overwrite_raw=True`)
- `run_production_pipeline.py` 的 `OHLCV_PATH` 改写 `data/live/`
- `download_data.py` 默认写 `data/live/`, 加 `--rebuild-baseline` flag 才写 `data/raw/`

### C. loader sha 硬阀门 (治标)

- `load_csv` 加 `strict_sha` 参数: 训练/复现路径 (`runner.py`) 传 `strict_sha=True`, sha 不符直接 raise
- 实时推理路径保持 `False` (实时数据本就会变)
- "A 防君子 (物理隔离), C 防小人 (训练侧硬崩)"

### D. gitignore + 文档

- `.gitignore` 加 `data/live/`, 防实时数据被 commit 回来
- 本文档留痕

---

## 4. 操作守则 (给未来的自己)

1. **VPS 下数据只下 onchain / live, 绝不碰 `data/raw/` 基准**
2. **`git pull` 后第一件事: 校验 btc 基准 sha == `004bf07...`**
3. **任何 `pull` 带 `data/raw/` 改动 = 红灯, 停下来查**
4. **重建基准是慎重操作**: 显式 `--rebuild-baseline` + 更新所有 config 的 `expected_sha256`
5. **生产信号用 `data/live/`, 训练/复现用 `data/raw/`, 两者永不混用**

---

## 5. 验证

修复后 E20c 复现守门通过 (model sha `8e34812f...` bit-exact), 复现链完整。
downloader 守卫 + loader strict_sha 已加单测覆盖 (见 `tests/`)。

---

*本文档与 lesson_0601 同系列, 均为数据治理 (Layer 0) 红线事件.*

---

## 6. 后续 (2026-06-05): 整改只做了一半 → 路径精神分裂

> **触发**: VPS `run_daily_nodock.sh` 在 stage 3.validate_data 报
> `DataFreshnessError: OHLCV 过期 last_date=2026-06-01 落后 4 天`,
> 但 stage 1 下载明明成功 (end=2026-06-05)。

**根因**: §3.A 路径隔离当时只改了「写端」(downloader / pipeline 下载 stage 写
`data/live/`), **读端没跟上**:

| 环节 | 改前读取 | 问题 |
|---|---|---|
| `data_freshness.OHLCV_PATH` | `data/raw/` | 校验旧基准 → 误报过期 |
| `live_signal.fetch_latest_data` | config 的 `data/raw/` | 推理吃旧基准 |
| `build_signal_json` 默认 | `data/raw/` | JSON 用旧价格 |
| `enrich_llm_analysis.OHLCV_PATH` | `data/raw/` (注释却写「与 pipeline 对齐」) | 名实不符 |

下载写 `live/`、校验/推理读 `raw/` → freshness gate 忠实地发现「即将推理的数据过期」,
报错没冤枉谁, 但根因是路径分裂而非数据真过期。

**修复**: 新增 `src/serving/paths.py` 作为 live 链路径**单一真相源**
(`LIVE_OHLCV_PATH` / `FGI_PATH` / `BASELINE_OHLCV_PATH`), 上述 4 处读端全部改 import 它。
`fetch_latest_data` 读取优先级改为 `data/live/` → config 基准 → 在线拉取。

**教训升级**: 路径隔离这种「写端/读端」对称的改动, 必须**两端一起改 + 收敛到单一常量**,
否则就是把一个 DRY 违规拆成两个各写各的。验证: `test_data_freshness` 7/7 通过,
三处路径常量 (`data_freshness` / `pipeline` / `paths`) assert 相等。
