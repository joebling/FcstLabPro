# 市场展示数据同步 (market data sync)

> 独立 best-effort 任务，刷新 dashboard **市场页**的展示数据。
> **与信号 pipeline 完全解耦** —— 它挂了只影响市场图，信号毫发无伤。

## 这是什么 / 为什么独立

市场页有 4 个展示数据源，**不是**生产模型 (E1/E8) 的特征（模型只吃 OHLCV + FGI）：

| 源 | 来源 | 输出文件 (gitignored) | 备注 |
|---|---|---|---|
| 资金费率 | crypto-market-data (GitHub) | `data/external/cmd_funding.csv` | 全市场聚合, 2022-12起 |
| 持仓量 | crypto-market-data (GitHub) | `data/external/cmd_open_interest.csv` | 全市场聚合 USD |
| taker买卖比 | crypto-market-data (GitHub) | `data/external/cmd_taker_ratio.csv` | **非**多空账户比 |
| 宏观 | Yahoo Finance (yfinance) | `data/external/macro_factors.csv` | 全量历史 (2018起), 覆盖自愈 |

> **为什么不用 Binance 期货?** funding/OI/多空比原走 `fapi.binance.com`,
> 但部分地区 (含本 VPS) 被 Binance **451 地域封锁**衍生品, 且期货**无公开镜像**
> (现货靠 data-api.binance.vision 才活)。改用 GitHub 托管的 crypto-market-data
> (CryptoQuant 口径全市场聚合), 不被 451, 每日自动更新, VPS 只需 git pull。
>
> **口径不同**: 全市场聚合数字/符号与币安单家不同, 故写入独立 `cmd_*.csv`,
> **不污染**研究基准 `funding_rate_BTCUSDT.csv` 等 (那些保持原 Binance 口径, 复现可靠)。
>
> **署名 (强制, CC BY 4.0)**: 市场页底部署名 Ercin Dedeoglu - Crypto Market Data。

按操作手册 Layer 0 边界，展示数据本就在模型链路之外，故另起独立 job，
不塞进信号 pipeline（避免 yfinance 抽风拖累信号命脉）。

> **FGI 不在此处刷** —— 它是生产特征，由信号 pipeline `run_production_pipeline.py`
> stage 2 每日下载（单一真相源，勿重复）。

## 前提: crypto-market-data 仓库

衍生品数据来自 https://github.com/ErcinDedeoglu/crypto-market-data，
需 clone 到**与 FcstLabPro 同级**的目录 (或设 `CRYPTO_MARKET_DATA_DIR` 指向其位置):

```bash
cd ~ && git clone https://github.com/ErcinDedeoglu/crypto-market-data.git
# 结果: ~/FcstLabPro 与 ~/crypto-market-data 同级
```

`run_market_data.sh` 每次会先 `git -C <repo> pull --ff-only` 拉最新 JSON,
再由 `sync_market_data.py` 转成 `cmd_*.csv`。pull 失败则用本地旧 JSON (best-effort)。

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

## git 冲突治理

- `cmd_*.csv` (funding/OI/taker) 已 **gitignored** (再生展示数据, 同 data/live 理念),
  不进 git → 不会跟 `git pull` 打架。
- `macro_factors.csv` 仍 **git-tracked** (兼任研究特征输入), 本 job 会改写它。
  拉代码前先丢弃再 pull (下次 sync 自动重灌):

```bash
git checkout -- data/external/macro_factors.csv && git pull
```

## 已知限制 (诚实告知)

- **衍生品数据与币安口径不同**：crypto-market-data 是 CryptoQuant 口径全市场聚合，
  funding 符号/尺度、OI 量级（约币安单家数倍）与原 Binance 不同。这是口径差异，非 bug。
- **taker 买卖比 ≠ 多空账户比**：它是成交主动买/卖量比，是情绪近亲，市场页据实标「taker买卖比」。
- **funding 显示尺度**：CMD funding 原生值约 ±0.003~0.006，市场页 KPI ×100 显示为 ±0.3~0.6%。
  偏大但因是全市场聚合口径；若观感不对可加显示因子微调。
- **无 SLA**：crypto-market-data 是社区项目（“随时可能停”）。它哪天停更 →
  `_is_fresh` 判陈旧 → 市场页自动标「陈旧」徽章（纵深防御）。
- macro (yfinance) 未被封，重跑即拉回全量历史。
- 市场页每个面板有「数据截止 {date}」徽章 + 超 4 天黄字告警（纵深防御）。
- 任务成功判定用 `_is_fresh` (最新日期超 4 天即判失败)，
  识破 “数据陈旧/未 pull” 的假成功。VPS 上 `run_market_data.sh` 会先 git pull 保鲜。

## 相关文件

| 文件 | 作用 |
|---|---|
| `scripts/sync_market_data.py` | 单入口，逐源刷新 (复用现成下载函数, DRY) |
| `scripts/sync_binance_oi_ls.py` | `sync_oi_ls()` 可 import 入口 (merge 累积 OI/LS) |
| `deploy/vps/run_market_data.sh` | VPS 包装 (.env + 线程 + 退出码) |
| `src/dashboard/data/market.py` | 市场页读取 + 新鲜度标注 |
| `tests/test_sync_market_data.py` | best-effort 隔离 / 退出码 / 列名回归 |
