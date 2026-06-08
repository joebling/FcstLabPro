# Production E1 vs v0529_E1_endfix 差异评审

**日期**: 2026-05-29  
**评审对象**: 当前 production E1 (`models/production/e1-conservative`) vs 新实验 `v0529_E1_endfix`  
**评审目的**: 判断修复 `data.start/end` 后重新训练的 E1 与当前线上 E1 有哪些实际差异，是否适合后续 promote。

---

## 1. 一句话结论

`v0529_E1_endfix` 是在修复 `load_csv()` 对 `data.start/end` 的过滤逻辑后，重新训练得到的 E1。

它和当前 production E1 的核心区别不是 feature 变化，也不是参数调优，而是：

```text
当前 production E1:
  config 声明 end=2025-12-31，
  但旧训练代码实际忽略了 end，读取了当时 CSV 的全部数据。

v0529_E1_endfix:
  config 声明 end=2025-12-31，
  新训练代码严格执行 end 过滤，训练数据实际截到 2025-12-31。
```

因此，`v0529_E1_endfix` 更符合 config 和研究规范，但它不是无影响替换：当前最新线上信号会从 `SILENT` 变成 `BUY`。

---

## 2. 背景：为什么会有这个版本

### 2.1 原问题

旧版 `src/data/loader.py::load_csv()` 只接受 `path`：

```python
df = load_csv(data_path)
```

虽然 config 中写了：

```yaml
data:
  start: '2018-01-01'
  end: '2025-12-31'
  path: data/raw/btc_binance_BTCUSDT_1d.csv
```

但旧代码没有把 `start/end` 传入 loader，也没有在 loader 内过滤日期。

结果是：

```text
config 中存在 data.end ≠ 训练代码实际使用 data.end
```

这属于 data contract violation。

### 2.2 修复后逻辑

现在 `load_csv()` 支持：

```python
load_csv(path, start=None, end=None)
```

并且 runner 会传入：

```python
df = load_csv(
    data_path,
    start=data_cfg.get("start"),
    end=data_cfg.get("end"),
)
```

所以 `v0529_E1_endfix` 的训练日志明确显示：

```text
数据加载完成: btc_binance_BTCUSDT_1d.csv
时间范围 2020-01-01 ~ 2025-12-31
共 2192 条
```

---

## 3. 数据范围差异

| 项目 | 当前 production E1 | v0529_E1_endfix |
|---|---|---|
| Config `data.end` | `2025-12-31` | `2025-12-31` |
| 训练时是否执行 `end` 过滤 | ❌ 否，旧代码忽略 | ✅ 是，新代码执行 |
| 实际训练读取范围 | 当时 CSV 全量，约至 `2026-02-17` | 严格至 `2025-12-31` |
| 数据契约一致性 | ❌ config 与执行不一致 | ✅ config 与执行一致 |

注意：当前活动 CSV 已更新到 `2026-05-28`，但 `v0529_E1_endfix` 不会吃到 2026 年数据，因为 `data.end=2025-12-31` 已生效。

---

## 4. 模型 lineage 差异

| 项目 | 当前 production E1 | v0529_E1_endfix |
|---|---|---|
| 路径 | `models/production/e1-conservative` | `experiments/weekly/v0529_E1_endfix` |
| 来源实验 | `weekly_bear_v0305_E1_decontam` | `v0529_E1_endfix` |
| 创建时间 | `2026-03-01T10:35:07.466035` | `2026-05-29T03:23:48.232198` |
| model hash | `4ca65e75f1df1b72` | `98c85910852e59a6` |

结论：两个模型二进制不同。`v0529_E1_endfix` 不是原模型的 metadata 修正，而是重新训练后的新模型。

---

## 5. 特征契约对比

| 项目 | 当前 production E1 | v0529_E1_endfix |
|---|---:|---:|
| 特征数 | 129 | 129 |
| `feature_cols` sha256 前缀 | `761edbd4b124736f` | `761edbd4b124736f` |

结论：特征列完全一致。模型差异主要来自训练样本范围变化，而不是特征工程漂移。

---

## 6. 分类指标对比

| 指标 | 当前 production E1 | v0529_E1_endfix | 变化 |
|---|---:|---:|---:|
| Accuracy | 0.8732993197 | 0.8781072177 | +0.0048078980 |
| F1 Binary | 0.4141546527 | 0.4160688666 | +0.0019142139 |
| Precision Binary | 0.3959899749 | 0.4084507042 | +0.0124607293 |
| Recall Binary | 0.4340659341 | 0.4239766082 | -0.0100893259 |
| Cohen Kappa | 0.3432908913 | 0.3480464753 | +0.0047555840 |

### 解读

`v0529_E1_endfix` 分类指标整体小幅改善：

- Accuracy 略升
- Kappa 略升
- Precision 明显一些提高
- Recall 略降

这说明新模型更谨慎一些，命中率略好，但会少抓一部分正例。

---

## 7. 保守策略 PnL 对比

对比目标策略：

```text
策略(止盈+regime)
```

这是 production active.yaml 中 E1 对应的 conservative variant。

| 指标 | 当前 production E1 | v0529_E1_endfix | 变化 |
|---|---:|---:|---:|
| Total Return | 0.3667041877 | 0.3638978837 | -0.0028063040 |
| CAGR | 0.0981402274 | 0.1030454315 | +0.0049052041 |
| Sharpe | 0.6332609304 | 0.6375080205 | +0.0042470901 |
| Max Drawdown | -0.1266007016 | -0.1266007016 | 约不变 |
| Profit Factor | 1.3183484390 | 1.2997635208 | -0.0185849181 |
| Exposure | 0.1362889984 | 0.1506493506 | +0.0143603523 |

### 解读

PnL 差异不大：

- 新模型 CAGR 和 Sharpe 略高
- Total Return 基本持平，略低
- MaxDD 几乎不变
- PF 略低
- Exposure 稍高

从 PnL 看，`v0529_E1_endfix` 不是压倒性优于当前 production E1，而是一个更契约正确、指标小幅变化的替代版本。

---

## 8. 最新信号差异

使用相同最新数据、相同 conservative 模式：

```bash
--take-profit --regime-switch --dry-run
```

结果：

| 模型 | 最新信号 | 价格 | Regime | 原因 |
|---|---|---:|---|---|
| 当前 production E1 | `SILENT` | `$73,428.94` | 非熊市 | `无信号: y_pred=0` |
| v0529_E1_endfix | `BUY` | `$73,428.94` | 非熊市 | `模型信号: y_pred=1` |

### 解读

这是最重要的行为差异。

虽然分类/PnL 指标变化不大，但当前最新线上信号已经分歧：

```text
production E1: SILENT
v0529_E1_endfix: BUY
```

因此如果直接 promote `v0529_E1_endfix`，当前生产行为会立刻改变。

---

## 9. 这是不是未来函数问题？

严格说，不是典型的 `feature[t]` 偷看 `future[t+1]`。

它更准确地说是：

```text
实验配置声明的样本截止日，与训练代码实际使用的样本截止日不一致。
```

属于：

```text
data contract violation / experiment boundary mismatch
```

旧 production E1 在 2026-03-01 左右训练时，确实可能已经能看到 2026-02-17 之前的数据，所以它不一定是时间穿越式泄露。

但从机构研究治理角度，它仍然有问题，因为：

1. config 说截止 `2025-12-31`
2. report/manifest 会让人以为只用了这个窗口
3. 旧代码实际用了 CSV 里的更多数据
4. 复现和审计时会产生错觉

`v0529_E1_endfix` 修复的是这个契约不一致问题。

---

## 10. 是否建议 promote？

### 支持 promote 的理由

- 数据边界逻辑正确
- config 与实际训练一致
- 分类指标小幅改善
- PnL 大体持平
- 特征契约未变，迁移风险相对可控

### 不建议直接 live promote 的理由

- 最新线上信号会从 `SILENT` 变成 `BUY`
- E1 是 primary/live 模型，不是 paper 模型
- PnL 改善不明显，不构成强制替换理由
- 需要观察新模型是否系统性更激进，因为 Exposure 从 13.63% 上升到 15.06%

---

## 11. 推荐下一步

不建议直接覆盖 production。

推荐按新 SOP 走 shadow / candidate 流程：

```text
1. 保留当前 production E1 不动
2. 将 v0529_E1_endfix 作为 candidate / shadow 模型
3. 每日生成 shadow signal
4. 对比 production E1 vs v0529_E1_endfix 的信号差异
5. 观察至少数周，再决定是否 promote
```

示例 shadow 命令：

```bash
.venv/bin/python scripts/live_signal.py \
  --model experiments/weekly/v0529_E1_endfix/model.joblib \
  --config experiments/weekly/v0529_E1_endfix/config.yaml \
  --take-profit \
  --regime-switch \
  --ledger-mode shadow \
  --dry-run
```

注意：如果要真正写 shadow ledger，不要加 `--dry-run`。

---

## 12. Review checklist

- [ ] 确认 `metrics.json` 指标变化可接受
- [ ] 确认 `pnl_metrics.json` 中 conservative variant 风险可接受
- [ ] 确认 Exposure 上升是否符合风控预算
- [ ] 确认当前 `BUY` vs production `SILENT` 的信号分歧是否可接受
- [ ] 若考虑 promote，先执行 dry-run promote
- [ ] 若覆盖 production，必须使用：

```bash
--overwrite-production --confirm-name e1-conservative
```

---

## 13. 结论

`v0529_E1_endfix` 是更符合数据契约的 E1 修正版，但它会改变当前线上信号。

推荐结论：

```text
先 shadow，不直接 live promote。
```

如果 shadow 结果稳定，再按 `docs/ops/model_promotion_sop.md` 执行正式晋升。
