FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖（git 用于安装 Orion-BiX，libgomp = OpenMP）
RUN apt-get update && apt-get install -y --no-install-recommends git libgomp1 && rm -rf /var/lib/apt/lists/*

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir scikit-learn==1.6.1

# 安装 CPU-only PyTorch (减少内存占用)
# 先安装 CPU 版本，再安装 Orion-BiX
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir git+https://github.com/Lexsi-Labs/Orion-BiX.git

# 拷贝项目（.dockerignore 控制排除内容）
COPY . /app

# 确保入口脚本有执行权限
RUN chmod +x /app/scripts/docker_entrypoint.sh

ENTRYPOINT ["/app/scripts/docker_entrypoint.sh"]
