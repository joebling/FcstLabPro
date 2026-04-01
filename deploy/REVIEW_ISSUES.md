# Deploy Script Review - 发现的问题

**Review 日期**: 2026-04-02

---

## 🔴 严重安全问题

| 位置 | 问题 | 风险 |
|------|------|------|
| `deploy.sh:100-102` | SMTP 密码明文硬编码 `SMTP_PASS=mlefgnksjkafbfei` | 凭证泄露到 Git/Cloud Build 日志 |
| `deploy.sh:104` | `GEMINI_API_KEY` Secret 名称硬编码 | 无灵活切换机制 |

---

## 🔴 高优先级问题

### 1. 凭证暴露
```bash
# 第 100-102 行
SMTP_PASS=mlefgnksjkafbfei
```
- 密码以环境变量形式传入 Job，可能被日志暴露
- **修复建议**: 使用 Secret Manager 存储

### 2. 镜像无版本控制
- 每次部署使用 `latest` 标签，无法回滚到特定版本
- **修复建议**: `IMAGE_TAG=${VERSION:-$(date +%Y%m%d)}`

---

## 🟡 中等问题

### 3. GCS Bucket 创建失败静默处理
```bash
# 第 74-76 行
gsutil mb -l "${REGION}" "gs://${BUCKET_NAME}" || true
```
- 创建失败时 `|| true` 会掩盖错误
- **修复建议**: 检查返回值或移除 `|| true`

### 4. Cloud Scheduler 未检查 Job 是否部署成功
- 第 124 行直接创建 scheduler，未验证 Step 2 成功
- **修复建议**: 添加 Job 存在性检查

### 5. Hardcoded 配置
- `REGION="asia-east1"` 不可配置
- `MEMORY="2Gi"`, `CPU="2"` 不可配置
- **修复建议**: 使用环境变量默认值

---

## ✅ 优点

1. **模型目录验证** (第 33-36 行) - 部署前检查必要文件
2. **从 manifest 读取信息** (第 38-40 行) - 动态获取模型指标
3. **参数化设计** - 支持 build/deploy/scheduler 分步执行

---

## 修复建议代码

```bash
# 1. SMTP 密码改为 Secret Manager
SMTP_PASS_SECRET="smtp-password"
--set-secrets="SMTP_PASS=${SMTP_PASS_SECRET}:latest"

# 2. 添加版本标签
IMAGE_TAG="${VERSION:-$(date +%Y%m%d)}"

# 3. 添加区域/资源可配置性
REGION="${REGION:-asia-east1}"
MEMORY="${MEMORY:-2Gi}"
```