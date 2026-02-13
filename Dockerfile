FROM python:3.13-slim

WORKDIR /app

# 安装 LightGBM 运行时依赖（libgomp = OpenMP）
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝项目（.dockerignore 控制排除内容）
COPY . /app

# 确保入口脚本有执行权限
RUN chmod +x /app/scripts/docker_entrypoint.sh

ENTRYPOINT ["/app/scripts/docker_entrypoint.sh"]
