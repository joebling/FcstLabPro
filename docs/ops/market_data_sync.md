# 市场展示数据同步 (market data sync)

> 独立 best-effort 任务，刷新 dashboard **市场页**的展示数据。
> **与信号 pipeline 完全解耦** —— 它挂了只影响市场图，信号毫发无伤。

## 这是什么 / 为什么独立

市场页有 4 个展示数据源，**不是**生产模型 (E1/E8) 的特征（模型只吃 OHLCV + FGI）：

| 源 | 文件 | API 能力 | 写盘 |
|---|---|---|---|
| 资金费率 | `data/external/funding_rate_BTCUSDT.csv` | 全量历史 (2019起分页) | 覆盖自愈 |
| 多空比 | `data/external/long_short_ratio_BTCUSDT.csv` | **仅最近 ~30 天** | merge 累积 |
| 持仓量 | `data/external/open_interest_BTCUSDT.csv` | **仅最近 ~30 天** | merge 累积 |
| 宏观 | `data/external/macro_factors.csv` (yfinance) | 全量历史 (2018起) | 覆盖自愈 |

按操作手册 Layer 0 边界，展示数据本就在模型链路之外，故另起独立 job，
不塞进信号 pipeline（避免 yfinance 抽风拖累信号命脉）。

> **FGI 不在此处刷** —— 它是生产特征，由信号 pipeline `run_production_pipeline.py`
> stage 2 每日下载（单一真相源，勿重复）。

## 怎么跑

```bash
# 本地 / 手动
python scripts/sync_market_data.py

# VPS (包了 .env 加载 + 线程限制)
deploy/vps/run_market_data.sh
```

每源独立 try/except：单源失败（如 yfinance）不传染其他源。
退出码：全部成功 = 0；任一源失败 = 1（供 cron/监控告警，已成功的源照常落盘）。

## 调度 (每 6 小时)

数据都是日频（funding 8h 结算 / OI·LS 日粒度 / macro 美股收盘后 / FGI 日更），
每小时纯属浪费 + Yahoo 限流风险。**每 6 小时**是甜点：自恢复瞬时失败 +
覆盖 funding 结算 + 美股收盘后刷到 macro。

> **`setup_vps_nodock.sh` 已自动注册这条 cron**（与信号 cron 一起，幂等去重）。
> 下面的手写行仅供参考 / 手动调整时用。

```cron
# crontab -e  (仓库克隆在 ~/FcstLabPro = /root/FcstLabPro; 与 run_daily_nodock.sh 同目录)
0 */6 * * * /root/FcstLabPro/deploy/vps/run_market_data.sh >> /opt/fcstlabpro/logs/market_data_$(date +%Y%m%d).log 2>&1
```

> 路径说明: `~/FcstLabPro` = 代码仓库 (git clone 位置, 含 shell 脚本);
> `/opt/fcstlabpro/` = 数据输出目录 (state/signals/logs), **里面没有代码**。
> 两者别混。脚本内部用 `BASH_SOURCE` 自算 REPO_DIR, 不依赖绝对路径;
> cron 里的绝对路径只需指向你实际克隆位置即可。

## git 冲突治理 (重要)

`data/external/*.csv` 是 **git-tracked**（兼任研究特征输入，保 committed 复现性 +
fresh-clone 安全网，故**不** gitignore）。但本 job 会原地改写它们 → VPS 上跟
`git pull` 打架。治理：**拉代码前先丢弃本地再生数据，再 pull**（下次 sync 自动重灌）：

```bash
git checkout -- data/external/*.csv && git pull
```

## 已知限制 (诚实告知)

- **OI / 多空比的历史无法回补**：Binance 接口只给最近 ~30 天。
  从部署当天起 `merge_and_save` 逐日累积，中间的历史洞补不了 —— 数据源硬限制，非 bug。
- funding / macro 无此问题，重跑即拉回全量历史。
- 市场页每个面板有「数据截止 {date}」徽章 + 超 4 天黄字告警（纵深防御），
  万一某源静默死了，一眼可见图旧没旧。

## 相关文件

| 文件 | 作用 |
|---|---|
| `scripts/sync_market_data.py` | 单入口，逐源刷新 (复用现成下载函数, DRY) |
| `scripts/sync_binance_oi_ls.py` | `sync_oi_ls()` 可 import 入口 (merge 累积 OI/LS) |
| `deploy/vps/run_market_data.sh` | VPS 包装 (.env + 线程 + 退出码) |
| `src/dashboard/data/market.py` | 市场页读取 + 新鲜度标注 |
| `tests/test_sync_market_data.py` | best-effort 隔离 / 退出码 / 列名回归 |
