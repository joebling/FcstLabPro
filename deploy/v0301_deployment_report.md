# FcstLabPro v0301 部署报告

**生成时间**: 2026-02-19

---

## 一、版本信息

| 项目 | 值 |
|------|-----|
| 版本 | v0301 |
| 部署日期 | 2026-02-19 |
| Job 名称 | `daily-btc-signal-v0301` |
| 镜像 | `fcstlabpro-v0301` |

---

## 二、模型配置

### Bull 模型 (v4 Extended OOS)

| 项目 | 值 |
|------|-----|
| 模型目录 | `experiments/weekly/weekly_bull_v27_orion_v4_extended_oos` |
| 模型类型 | Orion-BiX |
| 预测窗口 T | 21 天 |
| 标签策略 | reversal |
| init_train | 800 天 |
| 测试集时长 | 3.4 年 |

### Bear 模型

| 项目 | 值 |
|------|-----|
| 模型目录 | `experiments/weekly/weekly_bear_v13_T28_fgi_20260215_134804_ff4ad7` |
| 模型类型 | LightGBM |
| 预测窗口 T | 28 天 |
| 标签策略 | reversal |

---

## 三、关键改进 (v0218 → v0301)

| 项目 | v0218 | v0301 | 改进 |
|------|-------|-------|------|
| **Scaler 泄露** | 有 (全局 fit) | ✅ 已修复 (每步 refit) | 关键修复 |
| **IC t-stat** | -0.90 | **4.75** | ✅ 显著提升 |
| **测试集时长** | 1.4 年 | **3.4 年** | +143% |
| **样本数量** | 24 | **58** | +142% |

---

## 四、Institutional 指标达标情况

| 指标 | 目标 | v0301 结果 | 状态 |
|------|------|-----------|------|
| Rank IC | > 0.05 | 0.65 | ✅ |
| IC p-value | < 0.05 | 0.0000 | ✅ |
| IC t-stat | > 2 | 4.75 | ✅ |
| OOS Sharpe | > 1.0 | 1.24 | ✅ |
| Max DD | < 25% | 13.96% | ✅ |
| 测试集时长 | > 3 年 | 3.4 年 | ✅ |
| Non-overlap 样本 | > 50 | 58 | ✅ |
| Kappa > 0 比例 | > 70% | 70.7% | ✅ |

**结论**: ✅ 所有 Institutional 指标达标

---

## 五、策略配置

| 项目 | 值 |
|------|-----|
| 信号反转 | true |
| 三重 MA 过滤 | MA50 + MA150 + MA200 |
| 持仓期 | 14 天 |
| Bull 阈值 | 0.50 |
| Bear 阈值 | 0.50 |

---

## 六、部署步骤

```bash
# 1. 赋予执行权限
chmod +x deploy/deploy_v0301.sh

# 2. 执行部署 (完整流程)
./deploy/deploy_v0301.sh

# 3. 仅构建镜像
./deploy/deploy_v0301.sh build

# 4. 仅部署 Job
./deploy/deploy_v0301.sh deploy

# 5. 仅设置定时
./deploy_v0301.sh scheduler
```

---

## 七、验证命令

```bash
# 手动触发
gcloud run jobs execute daily-btc-signal-v0301 --region asia-east1

# 查看日志
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="daily-btc-signal-v0301"' \
  --limit=20

# 暂停调度
gcloud scheduler jobs pause daily-btc-signal-v0301-trigger --location=asia-east1
```

---

## 八、回滚方案

如需回滚到 v0218:

```bash
# 1. 重新部署 v0218
./deploy/deploy_v0218.sh

# 2. 或手动触发 v0218
gcloud run jobs execute daily-btc-signal-v0218 --region asia-east1
```

---

**报告生成**: 2026-02-19
