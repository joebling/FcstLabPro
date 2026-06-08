# Weekly Bear 实验总结

> 最后更新: 2026-05-29 | 当前 SOTA: **E16b** (SG 仅 close 平滑)
>
> 归档说明: 旧实验目录已移动到 `experiments/archive/`，`weekly/` 仅保留生产源、当前候选、复现验证与文档。

## 实验总览

| 实验 | 描述 | Accuracy | F1 | Precision | Recall | Kappa | 备注 |
|------|------|----------|-----|-----------|--------|-------|------|
| E1   | decontam 基线 | 0.8733 | 0.4142 | 0.3960 | 0.4341 | 0.3433 | 保守策略 |
| E2   | directional_pure | — | — | — | — | — | 已归档 |
| E3   | tb_grid_a | — | — | — | — | — | 已归档 |
| E4   | tb_grid_b | — | — | — | — | — | 已归档 |
| E5   | low_threshold | — | — | — | — | — | 已归档 |
| E6   | no_ma_filter | — | — | — | — | — | 已归档 |
| E7   | rsi50_only | — | — | — | — | — | 已归档 |
| E8   | touch_label | 0.9226 | 0.7991 | 0.7974 | 0.8009 | 0.7512 | 前 SOTA |
| E9   | touch_low_threshold | — | — | — | — | — | 已归档 |
| E10  | touch + real FR | — | — | — | — | — | 已归档 |
| E11  | touch + macro | — | — | — | — | — | 已归档 |
| E12  | touch + FR + macro | — | — | — | — | — | 已归档 |
| E13  | touch pruned light | — | — | — | — | — | 已归档 |
| E14  | touch pruned heavy | — | — | — | — | — | 已归档 |
| E15  | SG 全列 (w=11, p=3) | 0.9053 | 0.7767 | 0.7635 | 0.7905 | 0.7167 | 已归档 |
| E16a | SG 价格列 (w=7, p=2) | 0.9189 | 0.8116 | 0.7643 | 0.8652 | 0.7602 | 已归档 |
| **E16b** | **SG 仅 close (w=11, p=2)** | **0.9178** | **0.8176** | **0.7995** | **0.8366** | **0.7646** | **⭐ 新 SOTA** |
| E16c | SG 全列 (w=21, p=3) | 0.8920 | 0.7515 | 0.7481 | 0.7549 | 0.6825 | 已归档 |

## 当前最佳: E16b

- **配置**: touch_filtered 标签 + Savitzky-Golay 因果平滑 (仅 close, window=11, polyorder=2)
- **相对 E8 提升**: Kappa +1.3%, F1 +1.9%, Recall +3.6%
- **配置路径**: `configs/experiments/weekly/exp_weekly_bear_v0308_E16b_savgol_close.yaml`

## v0308 SG 平滑消融实验结论

灵感来源: arXiv:2506.05764v2 (Wang, 2025) — "数据预处理比模型复杂度更重要"

### 关键发现

1. **只平滑 close 列效果最佳**
   - volume 是离散脉冲信号，不适合连续平滑 → 平滑后反而丢失信息
   - high/low 包含重要的极值信息，平滑会抹掉波动特征
   - close 是最"连续"的价格信号，SG 平滑能有效去噪

2. **温和参数优于激进参数**
   - window=7~11 明显优于 window=21
   - polyorder=2 优于 3（更低阶 = 更平滑 = 去噪更彻底）
   - 日频数据噪声较低，不需要像论文中 100ms tick 数据那样强力去噪

3. **SG 平滑 + touch_label 的协同效应**
   - E16b (both) > E8 (touch only) > E15 (SG only with volume)
   - 标签策略和数据预处理是正交优化维度，可以叠加

4. **过度平滑的危害** (E16c)
   - window=21 在日频场景下跨度约 1 个月，平滑窗口已经接近预测窗口 (T=21)
   - 当 smoothing window ≈ label horizon 时，信号和噪声一起被抹掉

### 下一步方向

- [ ] E16b 晋升为生产模型候选 (`promote_model.py`)
- [ ] 对 E16b 做 PnL 回测验证实际交易表现
- [ ] 探索更多平滑方法 (EMA, Kalman Filter)
- [ ] 论文中的其他优化点: 序列拼接特征 (T×F flattening)

## 目录结构

```
experiments/weekly/
├── _docs/                                # 历史分析文档
├── consensus_E1_E8/                      # E1+E8 共识模型
├── v0529_E1_endfix/                      # E1 最新复现验证
├── v0529_E8_endfix/                      # E8 最新复现验证
├── weekly_bear_v0305_E1_decontam/        # 生产主模型源实验
├── weekly_bear_v0305_E8_touch_label/     # challenger 源实验
├── weekly_bear_v0308_E16b_savgol_close_only/ # SOTA 候选
└── SUMMARY.md                            # ← 你正在看的这个文件
```

已归档目录位于 `experiments/archive/`，包括 E2-E7、E9-E16a/E16c、E10-E14 与 v0301 空复查目录。
