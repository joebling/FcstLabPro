# Compute Engine VM 部署指南

## 为什么用 VM？

Cloud Run 的内存限制是 16Gi，对于我们的任务不够。Compute Engine VM 可以配置 **32Gi、64Gi 甚至更大内存**，立即解决 OOM 问题！

---

## 快速开始（3 步）

### 第 1 步：创建 VM

```bash
cd /Users/qiubling/Desktop/projects/FcstLabPro
chmod +x deploy/deploy_vm.sh
./deploy/deploy_vm.sh
```

这会创建一个：
- **8 vCPU + 32Gi 内存** 的 VM
- 基于 Ubuntu 22.04
- 自动安装 Docker

### 第 2 步：等待 VM 初始化

等待约 **2-3 分钟**，让 VM 完成初始化（安装 Docker 等）。

你可以通过以下命令检查 VM 状态：

```bash
gcloud compute instances describe fcstlabpro-signal-vm --zone asia-east1-a
```

### 第 3 步：运行任务

```bash
chmod +x deploy/deploy_vm_run.sh
./deploy/deploy_vm_run.sh
```

就这么简单！🎉

---

## 手动连接 VM（可选）

如果你想手动登录 VM 看看：

```bash
gcloud compute ssh fcstlabpro-signal-vm --zone asia-east1-a
```

在 VM 里，你可以：

```bash
# 检查 Docker
docker --version

# 拉取镜像
docker pull asia-east1-docker.pkg.dev/forecastlab-prod/fcstlabpro/fcstlabpro-0215:latest

# 运行容器
docker run --rm asia-east1-docker.pkg.dev/forecastlab-prod/fcstlabpro/fcstlabpro-0215:latest
```

---

## 设置定时任务（可选）

如果你想让 VM 每天自动运行任务，可以在 VM 里设置 cron：

```bash
# 连接到 VM
gcloud compute ssh fcstlabpro-signal-vm --zone asia-east1-a

# 编辑 crontab
crontab -e

# 添加这一行（每天北京时间 08:00 运行）
0 0 * * * docker run --rm asia-east1-docker.pkg.dev/forecastlab-prod/fcstlabpro/fcstlabpro-0215:latest >> /var/log/fcstlabpro.log 2>&1
```

---

## 成本估算

| 资源 | 配置 | 月成本（估算） |
|-----|------|--------------|
| VM | n2d-standard-8 (8 vCPU, 32Gi) | ~$120/月 |
| 磁盘 | 50GB | ~$2/月 |
| **总计** | | **~$122/月** |

*注：这是 24/7 运行的成本。如果只在需要时启动 VM，成本会更低。*

---

## 清理（不再需要时）

如果想删除 VM：

```bash
gcloud compute instances delete fcstlabpro-signal-vm --zone asia-east1-a
```

---

## 故障排查

### VM 创建失败

- 检查是否有足够的配额
- 尝试更换可用区（asia-east1-b, asia-east1-c）

### 任务运行失败

- 查看 VM 日志：
  ```bash
  gcloud compute instances get-serial-port-output fcstlabpro-signal-vm --zone asia-east1-a
  ```
- 连接到 VM 手动运行调试

---

## 对比：Cloud Run vs VM

| 特性 | Cloud Run | Compute Engine VM |
|-----|-----------|------------------|
| 最大内存 | 16Gi | 无限制（可配到 100+Gi） |
| 配置复杂度 | 简单 | 中等 |
| 成本 | 按使用付费 | 24/7 运行较贵 |
| 适用场景 | 轻量级任务 | 内存密集型任务 |

对于我们的任务（Orion-BiX 模型 + 大量特征计算），**VM 是更可靠的选择**！
