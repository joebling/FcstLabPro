# 论文对比分析: 2506.05764v2 vs FcstLabPro 现状

**论文**: "Exploring Microstructural Dynamics in Cryptocurrency Limit Order Books: Better Inputs Matter More Than Stacking Another Hidden Layer"  
**作者**: Haochuan Wang (UChicago, 2025)  
**分析日期**: 2026-03-08

---

## 一、论文核心发现

| # | 发现 | 描述 |
|---|------|------|
| 1 | **数据预处理 > 模型复杂度** | Savitzky-Golay 平滑一致性地提升所有模型 2-7% |
| 2 | **简单模型可以匹敌深度学习** | XGBoost/LR 在适当预处理后 ≈ DeepLOB 表现 |
| 3 | **SG滤波 >> Kalman >> 原始数据** | Kalman 有时甚至劣于原始数据 |
| 4 | **序列特征有价值** | T=10 比 T=1 提升约 2% 准确率 |
| 5 | **类别平衡很关键** | 逆频率加权 + 阈值调优显著影响结果 |
| 6 | **LOB深度 vs 覆盖率权衡** | 更深LOB=更高准确率但更少数据 |

---

## 二、FcstLabPro 现状与论文发现的 Gap 分析

### ✅ 已经做到的 (与论文一致)

| 方面 | FcstLabPro 现状 | 论文建议 | 匹配度 |
|------|----------------|---------|--------|
| **模型选择** | LightGBM (GBDT) | XGBoost/GBDT 足够 | ✅ 完全匹配 |
| **类别平衡** | `scale_pos_weight` 自动设置 | 逆频率加权 | ✅ 已实现 |
| **Walk-Forward** | 标准扩展窗口 WF | 真实 OOS 验证 | ✅ 已实现 |
| **特征工程丰富** | 12个特征集、100+特征 | 手工特征 + 自动特征 | ✅ 已实现 |
| **阈值优化** | `threshold_optimize` 可配置 | 阈值调优 | ✅ 已实现 |
| **Regime识别** | `regime` 特征集 + 样本加权 | 市场状态识别 | ✅ 已实现 |

### ❌ 关键 Gap (论文发现但项目未实现)

#### Gap 1: 🔴 **输入数据去噪/平滑 — 最大优化点**

- **论文发现**: Savitzky-Golay 滤波是所有实验中提升最大的单一因素
  - 二分类: 原始 0.65 → SG 平滑后 0.72 (+7%)
  - 三分类: 原始 0.44 → SG 平滑后 0.54 (+10%)
- **FcstLabPro 现状**: 直接用原始 OHLCV 数据构建特征，**没有任何去噪步骤**
  - `loader.py`: 仅做日期解析和去重
  - `builder.py`: 直接在原始 close/high/low 上计算技术指标
  - 没有 Savitzky-Golay 或 Kalman 滤波器
- **影响**: 噪声直接传递到所有下游特征（RSI、MACD、布林带等），降低信号质量
- **优先级**: 🔴 P0 — 投入产出比最高的优化

#### Gap 2: 🟡 **序列特征拼接 (Sequence Concatenation)**

- **论文发现**: 将 T 个时间步拼接为单一向量 (T×F → 1×TF) 喂入树模型，提升约 2%
- **FcstLabPro 现状**: `lag_rolling.py` 只为核心指标计算 lag/rolling 衍生，
  但没有做"将过去 N 天的原始特征向量拼接"的操作
- **区别**: lag 特征捕捉的是「指标变化趋势」，序列拼接捕捉的是「原始状态的时序模式」
- **优先级**: 🟡 P1 — 有价值但需要权衡特征维度爆炸

#### Gap 3: 🟡 **特征级去噪 (Feature-Level Denoising)**

- **论文发现**: 在计算特征之前先平滑原始数据，比在特征之后平滑效果更好
- **FcstLabPro 现状**: 技术指标中虽有 rolling mean，但这是指标本身的逻辑，不是去噪
- **优先级**: 🟡 P1 — 与 Gap 1 互补

#### Gap 4: 🟢 **自适应去噪窗口**

- **论文建议**: SG 滤波窗口可动态调整（论文用 window=21, degree=3）
- **FcstLabPro 现状**: 无相关机制
- **优先级**: 🟢 P2 — 在实现基础 SG 后再考虑

---

## 三、具体优化建议

### 建议 1: 添加 Savitzky-Golay 平滑预处理阶段 (P0)

**方案**: 在 `build_features()` 之前增加可配置的数据平滑步骤

```python
# src/features/smoothing.py
from scipy.signal import savgol_filter

def apply_savgol_smoothing(df, columns, window=21, polyorder=3):
    """对指定列应用 Savitzky-Golay 平滑."""
    for col in columns:
        if col in df.columns and len(df) > window:
            df[col] = savgol_filter(df[col], window, polyorder)
    return df
```

**配置集成**:
```yaml
features:
  smoothing:
    method: "savgol"   # "savgol" | "kalman" | "none"
    window: 21
    polyorder: 3
    columns: ["close", "high", "low", "volume"]
```

### 建议 2: 添加平滑后的特征集作为独立特征 (P1)

**方案**: 保留原始特征的同时，增加一组平滑后的特征作为"去噪视角"

```python
# 在 technical.py 中
df["close_sg"] = savgol_filter(close, 21, 3)
df["rsi_14_sg"] = calculate_rsi(df["close_sg"], 14)  # 平滑后的 RSI
```

### 建议 3: 特征维度控制 (P1)

- 论文建议: 特征过多反而降低性能（LOB从40层降到5层，覆盖率高但准确率低）
- 当前 FcstLabPro 有 100+ 特征，建议:
  - 基于 SHAP 做系统性特征选择
  - 或在 `builder.py` 中增加特征相关性过滤

---

## 四、实施路线图

| 阶段 | 内容 | 预期收益 | 工作量 |
|------|------|---------|--------|
| Phase 1 | 实现 `smoothing.py` + 配置集成 | 准确率 +2-5% | 1天 |
| Phase 2 | 创建平滑后特征集对比实验 | 验证效果 | 0.5天 |
| Phase 3 | 序列拼接特征 (可选) | 额外 +1-2% | 1天 |
| Phase 4 | 特征选择优化 | 鲁棒性提升 | 1天 |

---

## 五、注意事项

1. **SG 滤波有前瞻性**: `savgol_filter` 默认用双侧窗口，可能引入未来信息泄露
   - 解决方案: 使用 `mode='nearest'` 或只用单侧（causal）滤波
   - 或者在 walk-forward 中只对训练集做 fit，不 leak 到测试集

2. **论文场景 vs 项目场景差异**:
   - 论文: 100ms 级别高频 LOB 数据，噪声极大
   - FcstLabPro: 日频 OHLCV 数据，噪声相对较小
   - **但日频数据同样存在 flicker noise**，SG 平滑仍有价值

3. **不要过度平滑**: 日频数据 window=21 可能过大，建议从 window=7 或 11 开始实验
