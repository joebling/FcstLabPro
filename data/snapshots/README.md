# data/snapshots/ - VPS 实盘快照

**用途**: dashboard 双 check / 事故复盘 / 30 天回放. 把 VPS 上的实盘数据
(OHLCV + FGI + state JSONs) 定期 dump 到 git, 让本地能离线复盘.

**用法 (VPS 上)**:
```bash
# 抓当日快照 (dry-run, 只复制文件不 commit)
bash deploy/vps/dump_live_snapshot.sh

# 抓 + 自动 commit + push
bash deploy/vps/dump_live_snapshot.sh --commit
```

**命名约定**:
```
data/snapshots/
  btc_live_20260609.csv            # data/live/btc_binance_BTCUSDT_1d.csv 副本
  fgi_20260609.csv                 # data/live/fear_greed_index.csv 副本
  state_e20c-conservative-prune_20260609.json
  state_e8-touch_20260609.json
  reports/                         # 机器生成的常规报告 (每天起一份)
    pnl_replay_e20c-conservative-prune_20260609.md
    pnl_replay_e8-touch_20260609.md
```

日期 = UTC 当日, 每次 dump 都新文件不覆盖. git log 可看 dump 频率.

**reports/** 子目录是 `partial_bar_pnl_replay.py` 机器生成的报告,
每个非空 state 一份. 锁定为该脚本的官方输出地 — 别手动在这里添加人写报告 (那些放 docs/research/).

---

## 严禁用作

1. **训练基准** - `data/raw/btc_binance_BTCUSDT_1d.csv` 是 sha 锁定基准.
   snapshot 文件**不可** rename/copy 到 `data/raw/`, 也不能更新 config 的
   `expected_sha256` 指向 snapshot. 详见 `docs/lessons/lesson_0602_download_overwrite_baseline.md`.

2. **生产推理输入** - 推理走 `data/live/` (单一真相源), snapshot 只是只读副本.
   `live_signal.py::fetch_latest_data` 读取优先级里没有 snapshot, 别加.

## 设计原则 (lesson_0602 兼容)

- `data/raw/` = 不可变训练基准, sha 锁定, 只读
- `data/live/` = 实时下载落点, 可变, **gitignored**
- `data/snapshots/` = 定期 dump 的只读快照, **git tracked**, 用日期戳隔离每次 dump
- 三个目录用途互相独立, 永不混用

## 频率建议

- **手动**: 事故复盘前先 dump 一次, 让本地 agent 能精确复现
- **自动**: 每周 / 每月加 cron 跑一次 `--commit` (避免天天 commit 制造 git churn)
  ```bash
  # /etc/cron.d/fcstlab-snapshot 或 crontab -e
  0 1 * * 0  bash /root/FcstLabPro/deploy/vps/dump_live_snapshot.sh --commit \
                  >> /opt/fcstlabpro/logs/snapshot_$(date +\%Y\%m\%d).log 2>&1
  ```

---

*本目录由 lesson_0609 整改时新增 (2026-06-09).*
