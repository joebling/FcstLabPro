# Baseline Snapshot — 黄金复现基线

这个目录冻结了 **bit-exact 复现 E1/E8 生产模型所需的一切**，是
`scripts/verify_reproducibility.py` 的对账依据。

## 为什么需要它

2026-05-29 重构前做复现检查时发现 E1 Kappa 从 `0.3433` 漂到 `0.3669`。
根因有三个叠加：

1. **依赖未锁版本** — `requirements.txt` 全是 `>=` 下限锁，环境一升级就漂。
2. **数据被更新** — `data/raw/btc_binance_BTCUSDT_1d.csv` 是 git-tracked 的活动文件，
   基线之后被 append 了未来数据（2240 行 → 2340 行）。
3. **loader 曾忽略 config 的 `data.start/end`** — 已于 2026-05-29 修复：
   `runner.py` / `pnl_backtest_v0305.py` 现在都会把 config 的 `data.start/end` 传给 `load_csv()`。

所以「复现」必须同时冻结 **依赖版本** + **数据边界**，缺一不可。

## 内容

| 文件 | 说明 |
|------|------|
| `btc_baseline_693b7b1.csv` | 基线 commit `693b7b1` 时刻的 OHLCV 数据 (2240 行, 截至 2026-02-17；实际训练按 config.end 截至 2025-12-31, 2192 行) |
| `e1-conservative/metrics.json` | E1 黄金分类指标 (Kappa=0.3480464752792446) |
| `e1-conservative/fold_metrics.csv` | E1 各 fold 指标 |
| `e8-touch/metrics.json` | E8 黄金分类指标 (Kappa=0.7570656864311971) |
| `e8-touch/fold_metrics.csv` | E8 各 fold 指标 |

数据文件 SHA256: `9fafdc8f115c5f73b659c242bb787c4c2df025321e0ebbe6705800e949ccf731`

## 复现条件 (三者缺一不可)

1. **环境**: `requirements.lock.txt` (Py3.10 + LightGBM 4.3.0 + numpy 1.26.4 + sklearn 1.4.1)
2. **数据**: 本目录的 `btc_baseline_693b7b1.csv` + config 的 `data.start/end` 过滤 (有效窗口截至 2025-12-31)
3. **种子**: `seed=42` (config 内固定)

## 用法

```bash
# 一键验证 (重跑 E1/E8 并逐位对账)
.venv/bin/python scripts/verify_reproducibility.py

# 只验证单个模型
.venv/bin/python scripts/verify_reproducibility.py --model e1-conservative
```

✅ 已验证 (2026-05-29): E1/E8 全指标 `diff=0.00e+00`，bit-exact。

> ⚠️ 任何重构 / 代码修改后，**先跑这个脚本**确认数值未漂移，再继续。
> 这就是 CLAUDE.md §5.3 复现性验证流程的可执行版本。
