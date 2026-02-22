FROM python:3.10-slim

WORKDIR /app
ENV PYTHONPATH="/app:${PYTHONPATH}"

RUN apt-get update && apt-get install -y --no-install-recommends git libgomp1 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir scikit-learn==1.6.1

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir git+https://github.com/Lexsi-Labs/Orion-BiX.git

RUN date +%s > /tmp/build_timestamp.txt && echo "Build timestamp: $(date)"

COPY . /app

RUN chmod +x /app/deploy/docker_entrypoint_v0302.sh

ENTRYPOINT ["/app/deploy/docker_entrypoint_v0302.sh"]
