#!/usr/bin/env bash
# 探测 BGeometrics CDN 是否可作为生产数据源
# 在 VPS 上跑: bash scripts/probe_bgeometrics_cdn.sh

set -u
BASE="https://charts.bgeometrics.com/files"

# 核心 LTH/STH 指标
FILES=(
  "lth_mvrv"
  "sth_mvrv"
  "lth_nupl"
  "sth_nupl"
  "lth_sopr"
  "sth_sopr"
  "mvrv_data"
  "mvrv_zscore_data"
  "nupl_data"
  "aviv"
  "reserve_risk"
)

echo "=== HEAD 请求测试 (status + size + last-modified) ==="
printf "%-25s %-7s %-12s %s\n" "file" "status" "size_KB" "last_modified"
echo "---------------------------------------------------------------------------"
for f in "${FILES[@]}"; do
    URL="$BASE/${f}.json"
    resp=$(curl -s -I --max-time 10 "$URL" 2>&1)
    status=$(echo "$resp" | head -1 | awk '{print $2}')
    size=$(echo "$resp" | grep -i 'content-length' | awk '{print $2}' | tr -d '\r')
    lm=$(echo "$resp" | grep -i 'last-modified' | cut -d' ' -f2- | tr -d '\r')
    size_kb=$(( ${size:-0} / 1024 ))
    printf "%-25s %-7s %-12s %s\n" "$f" "${status:-FAIL}" "$size_kb" "${lm:-?}"
done

echo ""
echo "=== 实际下载 lth_mvrv.json 验证内容 ==="
curl -s --max-time 30 "$BASE/lth_mvrv.json" -o /tmp/lth_mvrv_probe.json
if [ -s /tmp/lth_mvrv_probe.json ]; then
    size=$(wc -c < /tmp/lth_mvrv_probe.json)
    first_ts=$(python3 -c "import json; d=json.load(open('/tmp/lth_mvrv_probe.json')); print(d[0])" 2>/dev/null)
    last_ts=$(python3 -c "import json,datetime; d=json.load(open('/tmp/lth_mvrv_probe.json')); ts=d[-1][0]/1000; print(datetime.datetime.utcfromtimestamp(ts).date(), '→ value=', d[-1][1])" 2>/dev/null)
    echo "下载成功: $size bytes"
    echo "首条: $first_ts"
    echo "末条: $last_ts"
else
    echo "❌ 下载失败"
fi

echo ""
echo "=== 测试 BGeometrics REST API ==="
curl -s --max-time 10 -o /tmp/api_probe.json -w "HTTP=%{http_code} time=%{time_total}s\n" \
    "https://bitcoin-data.com/v1/mvrv-zscore/last" || echo "API 测试失败"
echo "返回内容:"
head -c 300 /tmp/api_probe.json
echo ""
