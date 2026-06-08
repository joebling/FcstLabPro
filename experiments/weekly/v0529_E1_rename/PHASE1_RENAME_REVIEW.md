# Phase 1 清污重命名 Review — v0529_E1/E8_rename

> **日期**: 2026-05-29
> **作者**: sam (code-puppy)
> **SOP**: 遵循 `docs/ops/experiment_sop.md` Stage 0-7
> **前置诊断**: `docs/reviews/cr_0522_feature_engineering.md` §P0-1/P0-2
> **路线图**: `docs/plans/feature_engineering_roadmap.md` Phase 1

---

## 1. 假设与范围

**假设**: 将 `market_structure.py` 中的伪外部命名特征重命名后,
分类指标与 PnL 应与 production 基线 **bit-exact** (纯重命名, 不改数值)。

**重命名映射**:

| 旧名 (误导) | 新名 (诚实) | 真实公式 |
|---|---|---|
| `funding_rate_{7,14,24}` | `price_mom_smooth_{7,14,24}` | `close.pct_change().rolling(w).mean()*100` |
| `open_interest_{7,14,24}` | `volume_cumsum_{7,14,24}` | `volume.rolling(w).sum()` |
| `stablecoin_inflow_proxy` | `down_volume_proxy` | `-close.pct_change(7)*volume.rolling(7).mean()` |

**严格范围控制 (对照原则)**:
- ✅ 只重命名, 不改算法
- ✅ 不启用真实 funding/macro 数据 (那是 Phase 2, 单独实验隔离归因)
- ✅ 不动 lag_rolling.py 的 mvrv/sopr (那是 onchain P0-2, 另算)

---

## 2. 结果: 完整 bit-exact

### 2.1 分类指标 (vs production golden)

| 指标 | E1 rename | E1 golden | diff | E8 rename | E8 golden | diff |
|---|---|---|---|---|---|---|
| accuracy | 0.8781072177 | 0.8781072177 | 0 | 0.9284216831 | 0.9284216831 | 0 |
| cohen_kappa | 0.3480464753 | 0.3480464753 | 0 | 0.7570656864 | 0.7570656864 | 0 |
| f1_binary | 0.4160688666 | 0.4160688666 | 0 | 0.8006672227 | 0.8006672227 | 0 |

### 2.2 predictions 逐行对账 (vs v0529 endfix 同窗口基线)

```text
E1: 3339 行逐行一致 = True
E8: 3339 行逐行一致 = True
```

### 2.3 PnL 止盈+regime 变体 (vs endfix)

| 模型 | cagr diff | sharpe diff | maxDD diff |
|---|---|---|---|
| E1 | 0.0e+00 | 0.0e+00 | 0.0e+00 |
| E8 | 0.0e+00 | 0.0e+00 | 0.0e+00 |

**结论: 纯重命名假设 100% 验证, LightGBM 列序 tie-break 不受影响。**

---

## 3. 关键发现: "0 PnL 风险" 是错的

roadmap 原文称 Phase 1 "纯重命名, 0 PnL 风险, 不需重训"。**实测推翻**:

```text
ValueError: 特征顺序不匹配 (共 7 处不同)
  index 96: expected='funding_rate_7', actual='price_mom_smooth_7'
  ...
[pipeline] FATAL — stage 4.signals 失败, halt
```

重命名后, production live 推理被 `validate_feature_cols` 守卫 **当场 halt** —
因为 production joblib/feature_cols 还记着旧名字。

**正确画像**: 重命名 = 改共享 feature builder = 必须重训 + 重新 bootstrap
feature_cols + 复现验证, 而非 "0 风险纯文字改动"。

守卫拦截是**正确行为** (没让脏模型悄悄出错信号), 体现 v0529 治理价值。

---

## 4. 当前状态与后续 (选项 A)

按选项 A: production 暂不刷新, 本实验作为 promotion candidate。

```text
✅ research 代码 market_structure.py → 新名字
✅ 新实验 E1/E8 → bit-exact candidate
⚠️ production joblib/feature_cols → 仍旧名字 → live 推理 halt
```

**⚠️ 重要: 当前 live 推理处于 halt 态。** 必须二选一尽快收口:

1. **promote 路线**: 走 `model_promotion_sop.md` 用本实验刷新 production
   (model.joblib + config + feature_cols 全部更新为新名字)
2. **回滚路线**: 若暂不 promote, 需 `git revert` 重命名 commit 让 live 恢复

不能停在中间态 — 否则 live 一直 halt。

---

## 5. Checklist

- [x] Stage 0 复现守门 (改动前绿)
- [x] step==T (21), purge_gap>=T (21)
- [x] 数据窗口 end=2025-12-31 一致
- [x] 分类指标 bit-exact
- [x] predictions 逐行一致
- [x] PnL bit-exact
- [x] 重命名副作用 (live halt) 已识别并记录
- [x] **promote 决策 (已落地): 走 promotion SOP 刷新 production e1-conservative + e8-touch,
  feature_cols 均为新名, live halt 解除; 2026-05-29 复现验证 bit-exact,
  manifest reproducibility_verified 已翻绿。**

---

*遵循 experiment_sop.md，未改动任何 production 文件。*
