#!/usr/bin/env bash
# FcstLabPro 内存监控脚本
# 监控 weekly_signal.py 运行时的内存使用

echo "开始监控内存..."
echo "PID: $$"

while true; do
    MEM=$(ps -o rss= -p $$ 2>/dev/null || echo "0")
    MEM_MB=$((MEM / 1024))
    echo "$(date '+%H:%M:%S') - 内存: ${MEM_MB} MB"
    sleep 5
done
