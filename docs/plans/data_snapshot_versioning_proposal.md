# 提案: 训练数据快照随模型版本走 (Data Snapshot Versioning)

> **日期**: 2026-06-02
> **作者**: sam (with Qiu)
> **状态**: 提案 (未实现)
> **背景**: lesson_0601 / lesson_0602 两次"训练基准被改导致复现链断裂"事故后, 讨论是否把训练数据快照和模型产物绑成不可变版本单元.

---

## 1. 核心问题

> 训练某模型的数据不大时, 数据是否可以跟着模型版本走?

**结论: 可以, 且强烈建议.** 数据小让这件事几乎零成本, 没理由不做.

更准确的表述:
- **"该不该跟版本走" 由复现需求决定** (机构级硬要求), 与数据大小无关.
- **数据大小只决定实现方式**: 小数据直接进 git; 大数据用 content-addressed 存储 + 指针 (DVC/git-lfs/对象存储).

---

## 2. 为什么要做 (动机)

### 2.1 现状痛点

```
config.data.path → data/raw/btc_binance_BTCUSDT_1d.csv  (共享, 可变)
    → 任何人动一下基准, 所有模型的复现全废
    → 2026-06-01 (lesson_0601) + 2026-06-02 (lesson_0602) 已为此救火两次
```

复现性目前靠 **纪律 + sha 校验** 维持 (易被绕过), 而非物理保证.

### 2.2 目标态

```
models/production/e20c/data_snapshot/btc.csv  (私有, 不可变)
    → E20c 永远 bit-exact 复现, 与外界基准变不变无关
    → 别的模型动数据, 物理上碰不到 E20c 的快照
```

**每个模型自带"时间胶囊", 复现性从"靠纪律"升级为"物理保证".**

---

## 3. 体量评估 (为何小数据让这件事零成本)

| 数据 | 体量 |
|---|---|
| btc 基准 csv | 251 KB |
| onchain 全部 (12 indicator) | 1.7 MB |
| FGI | ~30 KB |
| model.joblib (E20c) | 193 KB |
| **单模型完整快照 (btc+onchain+fgi)** | **~2 MB** |

晋升 100 个模型 = 200 MB 快照. git 无压力. **存储成本——"数据跟版本走"的唯一传统反对理由——在此被消灭.**

---

## 4. 三个实现层次 (从轻到重)

| Level | 快照内容 | 单模型增量 | 复现保证 | 评价 |
|---|---|---|---|---|
| L1 | 只 btc 基准 | 251 KB | 部分 (onchain 变了仍碎) | 纯技术面模型够用 |
| **L2** | **btc + onchain + fgi** | **~2 MB** | **完整** | ⭐ **推荐** |
| L3 | 全局去重快照区 `data/snapshots/{sha}/` + 指针 | 接近 0 (共享) | 完整 | YAGNI — 模型数量少时过度工程 |

**推荐 L2**: 完整时间胶囊, 体量无压力, 实现最直接, 不引入间接层.

---

## 5. 实现方案 (L2, 基于现有基础设施)

好消息: `promote_model.py` 已有大部分基础设施.

### 5.1 现有相关代码

| 已有 | 位置 |
|---|---|
| `files_to_copy` 复制模型产物 | `promote_model.py:241` |
| `build_data_manifest` 生成 sha 清单 | `promote_model.py:327` |
| `data_manifest.json` 已存 raw/effective 的 sha+rows+range | 每个生产模型目录 |

### 5.2 需要改的 (约 2 处)

**A. 晋升时复制训练快照** (`promote_model.py`):
```python
# 在 data_manifest 生成后, 新增:
snapshot_dir = target_dir / "data_snapshot"
snapshot_dir.mkdir(exist_ok=True)
# 复制 btc 基准
shutil.copy2(data_path, snapshot_dir / Path(data_path).name)
# 复制 onchain/fgi (从 config.features.sets 推断用到哪些)
for ext_file in _resolve_external_inputs(config):
    shutil.copy2(ext_file, snapshot_dir / ext_file.name)
```

**B. 复现/部署时优先读快照** (`runner.py` 或 `live_signal.py`):
```python
# 若模型目录有 data_snapshot/, 优先用它; 否则回退 config.data.path
snapshot = model_dir / "data_snapshot" / Path(config["data"]["path"]).name
data_path = snapshot if snapshot.exists() else config["data"]["path"]
```

### 5.3 manifest 增字段
```json
"data_snapshot": {
  "embedded": true,
  "files": ["btc_binance_BTCUSDT_1d.csv", "sopr_data.csv", ...],
  "total_bytes": 2097152
}
```

---

## 6. 与现有防护的关系 (互补, 非替代)

| 防护 | 作用 | 层次 |
|---|---|---|
| A 路径隔离 (lesson_0602) | live vs raw 不混用 | 防实时数据污染基准 |
| C strict_sha 硬阀门 | 训练时基准被改即崩 | 防静默错误 |
| **本提案 (数据快照随版本)** | **每模型自带不可变训练数据** | **复现物理保证** |

三者叠加: A+C 守住"共享基准"的卫生, 本提案则让"每个已晋升模型"彻底独立于共享基准. **即使共享基准哪天再次被毁, 已晋升模型仍能 bit-exact 复现.**

---

## 7. 取舍与风险

**优点**:
- 复现性物理保证, 不依赖纪律
- 模型自包含, 可单独归档/迁移
- git 天然版本控制 + 可回滚

**代价 / 注意**:
- git 仓库随模型数量线性增长 (~2MB/模型; 100 个 = 200MB, 可接受)
- 快照与 `config.data.path` 可能漂移 → 需 promote 时校验 sha 一致
- L3 的去重诱惑要克制 (YAGNI): 模型数量到几百个再考虑

**何时升级到 L3 (去重)**:
- 生产模型 > 100 个, 或单份数据 > 50 MB
- 此时改用 `data/snapshots/{sha256}/` content-addressed + manifest 存指针

---

## 8. 建议决策

- ✅ 体量小, 复现需求硬 → **采纳 L2**
- ⏸️ 实现时机: 可等 Wave 3 实验告一段落, 与下一次 promote 一起落地 (避免打断当前研究流)
- 📌 落地前必过 5.3 节复现验证 (E1/E8/E20c bit-exact)

---

*本提案与 lesson_0601/0602 同属 Layer 0 数据完整性治理.*
