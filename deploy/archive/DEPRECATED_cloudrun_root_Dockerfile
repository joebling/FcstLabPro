FROM python:3.10-slim

WORKDIR /app
ENV PYTHONPATH="/app:${PYTHONPATH}"

# 系统依赖: libgomp = LightGBM OpenMP
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

# Python 依赖 (无 PyTorch, 无 Orion-BiX)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt google-cloud-storage

# 强制重建层
RUN date +%s > /tmp/build_timestamp.txt

COPY . /app

# 通用入口脚本 (模型无关, 由 MODEL_NAME 环境变量控制)
RUN chmod +x /app/deploy/docker_entrypoint.sh

ENTRYPOINT ["/app/deploy/docker_entrypoint.sh"]
