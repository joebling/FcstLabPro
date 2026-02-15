# FcstLabPro 实验技巧手册

**版本:** 1.0
**更新日期:** 2026-02-15

---

## 1. 实验流程标准化

### 1.1 基础流程
```
1. 确定实验目标
   ├── 改善特征集 → 消融实验
   ├── 改善模型配置 → 网格搜索
   └── 改善标签策略 → 对比实验

2. 创建实验配置
   └── configs/experiments/weekly/exp_weekly_[bull|bear]_[version].yaml

3. 运行实验
   └── python scripts/run_experiment.py --config configs/experiments/...

4. 分析结果
   ├── metrics.json → 核心指标
   ├── feature_importance.csv → 特征重要性
   └── fold_metrics.csv → 交叉验证稳定性

5. 记录实验
   └── experiments/registry.json 自动记录
```

### 1.2 消融实验模板
```yaml
# 消融实验配置示例
features:
  sets:
    - technical
    - volume
    - flow
    - market_structure
    # 消融变量:
    # - external_fgi
    # - external_macro
    # - external_fr
```

---

## 2. v9-v12 实验经验总结

### 2.1 有效的方法
- **FGI 单独使用** - Kappa +24%
- **更长预测窗口** - T=21 让 Bull Kappa +56%

### 2.2 失败的尝试
- **FGI 特征增强** - 特征过多导致过拟合 (v10)
- **directional 标签** - 不适合当前特征集 (v11)
- **T=21 对 Bear 无效** - 上涨趋势更容易预测

### 2.3 关键教训
- 不要一次性加所有外部数据
- 不同模型需要不同超参数配置
- 部署前验证环境变量
- Bull/Bear 模型需要分别优化

---

## 3. 实验技巧

### 3.1 快速验证新特征
```bash
# 1. 创建消融实验配置
# 2. 用小规模配置快速验证 (n_estimators=500)
# 3. 确认有效后再优化
```

### 3.2 特征重要性分析
- 查看 `feature_importance.csv`
- 关注 FGI 相关特征是否入选
- 验证特征与价格的低相关性

### 3.3 对比实验设计
```
实验A: 基线 (无新特征)
实验B: 基线 + 特征X
实验C: 基线 + 特征Y
实验D: 基线 + 特征X + 特征Y

必须确保 A/B/C/D 其他条件完全一致
```

### 3.4 超参数敏感性
| 参数 | 建议范围 | 影响 |
|------|----------|------|
| n_estimators | 300-1500 | 更多 = 更稳定，但可能过拟合 |
| max_depth | 3-8 | 越深 = 越复杂 |
| learning_rate | 0.01-0.1 | 越小 = 需要更多树 |
| num_leaves | 8-64 | 控制模型复杂度 |
| reg_alpha/lambda | 0.1-1.0 | 正则化强度 |

---

## 4. 配置管理规范

### 4.1 命名规范
```
exp_weekly_bull_v9_fgi.yaml
  └── [type]_[model]_[version]_[feature].yaml
```

### 4.2 实验目录结构
```
experiments/weekly/
├── weekly_bull_v9_fgi_v2_20260215_113918_2181e7/
│   ├── config.yaml          # 实验配置
│   ├── metrics.json         # 核心指标
│   ├── model.joblib         # 训练好的模型
│   ├── feature_importance.csv
│   ├── fold_metrics.csv
│   └── predictions.csv
```

### 4.3 部署配置同步
- `scripts/weekly_signal.py` - 默认模型路径
- `scripts/docker_entrypoint.sh` - 默认模型路径
- `deploy/gcloud_deploy.sh` - 环境变量默认值

---

## 5. 常见问题排查

### 5.1 Kappa 为负
- 检查标签是否颠倒
- 检查特征是否与目标高度共线

### 5.2 消融实验效果不稳定
- 增加 Walk-Forward 窗口
- 检查数据泄露

### 5.3 部署后结果与本地不一致
- 检查特征构建是否使用相同数据源
- 验证外部数据是否同步更新

---

## 6. 下次实验检查清单

- [ ] 消融实验逐个验证
- [ ] 记录所有实验配置
- [ ] 对比时保持其他变量一致
- [ ] 部署前验证环境变量
- [ ] 写实验总结报告

---

*手册维护: FcstLabPro 实验团队*
