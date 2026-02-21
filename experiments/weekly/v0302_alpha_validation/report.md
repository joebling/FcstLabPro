# v0302 Alpha 验证实验报告

> 实验日期：2026-02-20
> 基于配置：exp_weekly_bull_v27_orion_v4_extended_oos

---

## 一、实验背景

验证 v0301 实验的结论是否可信，通过 10 个"毁灭性测试"检验模型真伪。

---

## 二、代码修复状态 (2026-02-20)

### 已修复的 Bug

| Bug ID | 描述 | 状态 |
|--------|------|------|
| C1 | 模型不一致 (RF → Orion-BiX) | ✅ 已修复 |
| C2 | E01 Pass/Fail 逻辑错误 | ✅ 已修复 |
| C3 | E02 收益对齐计算错误 | ✅ 已修复 |
| C4 | E03 MA 计算错误 | ✅ 已修复 |
| C5 | E10 采样逻辑错误 | ✅ 已修复 |

### 修复详情

- **C1**: 所有 11 个文件中的 `RandomForestClassifier` 替换为 `OrionBixClassifier(n_estimators=4, random_state=42)`
- **C2**: E01 增加 Real IC 显著性检查
- **C3**: E02 修正收益计算为 `close[idx+T]/close[idx]`
- **C4**: E03 先在日线数据上计算 MA，再索引
- **C5**: E10 先 non-overlap 采样，再按 regime 过滤

---

## 三、运行实验

### 运行命令

```bash
cd /Users/qiubling/Desktop/projects/FcstLabPro
source venv_py310/bin/activate

# 依次运行（每个约 15-30 分钟）
python experiments/weekly/v0302_alpha_validation/e01_random_label.py
python experiments/weekly/v0302_alpha_validation/e02_continuous_ic.py
python experiments/weekly/v0302_alpha_validation/e03_no_ma.py
python experiments/weekly/v0302_alpha_validation/e04_init_train_sensitivity.py
python experiments/weekly/v0302_alpha_validation/e05_newey_west.py
python experiments/weekly/v0302_alpha_validation/e06_bootstrap_ci.py
python experiments/weekly/v0302_alpha_validation/e07_multi_asset.py
python experiments/weekly/v0302_alpha_validation/e08_threshold_sensitivity.py
python experiments/weekly/v0302_alpha_validation/e09_horizon_sensitivity.py
python experiments/weekly/v0302_alpha_validation/e10_bear_regime.py
```

### 配置

```yaml
Model: OrionBixClassifier(n_estimators=4, random_state=42)
Walk-Forward: init_train=800, oos_window=63, step=21
Label: T=21, X=0.05
Features: 148
```

---

## 四、实验结论

**待运行后填写**

旧结论（RandomForest + Bug 版本）已删除，需要运行 Orion-BiX 版本后重新填写。

---

*报告更新：2026-02-20*
