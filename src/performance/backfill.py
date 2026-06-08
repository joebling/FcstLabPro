"""信号回填 — 对每条 archive 信号, 用真实未来价格算实现结果.

执行假设与 PnL 回测 (pnl_backtest_v0305) 一致: t_close 出信号,
t+1_open 进场, 持有 T 天后 close 出场。这样 live 实现结果与回测口径对齐。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.performance.maturity import is_mature, maturity_lag_days

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ARCHIVE_DIR = PROJECT_ROOT / "data" / "signals" / "archive"
OHLCV_PATH = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"


def load_archive_signals(model_name: str, archive_dir: Path | None = None) -> list[dict]:
    """读某模型的全部 archive 信号 (按日期升序)."""
    base = (archive_dir or ARCHIVE_DIR) / model_name
    if not base.exists():
        return []
    out = []
    for f in sorted(base.glob("*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, OSError):
            continue  # 坏文件跳过, 不让回填整体崩
    out.sort(key=lambda r: r.get("date", ""))
    return out


def load_ohlcv(path: Path | None = None) -> pd.DataFrame:
    """读 OHLCV, date 为 DatetimeIndex."""
    df = pd.read_csv(path or OHLCV_PATH, parse_dates=["date"])
    return df.set_index("date").sort_index()


def load_live_ohlcv() -> pd.DataFrame:
    """优先 data/live/ (实时下载落点), 缺失回退 data/raw/ 基准 (lesson_0602).

    live 链 (dashboard 展示 / 信号实现结果回填) 应读 data/live/ — 那是每日
    pipeline 的实时下载落点。读冻结的 data/raw/ 会让近期信号查不到出场日价
    而被误判 PENDING / 价格陈旧。本地开发 / 全新 checkout 没 live (.gitignore)
    时回退 baseline, 保证不崩。
    """
    from src.serving.paths import LIVE_OHLCV_PATH
    return load_ohlcv(LIVE_OHLCV_PATH if Path(LIVE_OHLCV_PATH).exists() else OHLCV_PATH)


def _slim(rec: dict) -> dict:
    """从 archive 记录提取展示/审计需要的精简字段."""
    prov = rec.get("provenance", {})
    return {
        "date": rec.get("date"),
        "signal": rec.get("signal"),
        "price": rec.get("price"),
        "regime": rec.get("regime"),
        "model_hash": prov.get("model_hash", ""),
        "strategy_variant": prov.get("strategy_variant", ""),
        "score_source": rec.get("score_source", ""),
    }


def backfill_outcomes(
    model_name: str,
    *,
    label_T: int,
    ohlcv: pd.DataFrame | None = None,
    archive_dir: Path | None = None,
    today=None,
) -> list[dict]:
    """对每条信号算实现结果.

    Parameters
    ----------
    model_name : 模型名 (archive 子目录)
    label_T : 标签窗口天数 (持有期), 用于成熟门控 + 出场点
    ohlcv : OHLCV (默认自动加载)
    today : 测试注入用 (date)

    Returns
    -------
    list[dict] : 每条带 status (MATURE/PENDING), 成熟时附实现结果。
    """
    signals = load_archive_signals(model_name, archive_dir)
    if ohlcv is None:
        ohlcv = load_ohlcv()

    lag = maturity_lag_days({"label": {"T": label_T}})
    idx = ohlcv.index
    out: list[dict] = []

    for rec in signals:
        slim = _slim(rec)
        d_str = rec.get("date")
        if not d_str:
            continue

        if not is_mature(d_str, lag, today=today):
            out.append({**slim, "status": "PENDING"})
            continue

        # 成熟: 进场 t+1 open, 出场 t+T close (与 PnL 回测一致)
        d = pd.Timestamp(d_str)
        pos = int(idx.searchsorted(d))
        entry_pos = pos + 1
        exit_pos = pos + label_T

        # 数据未覆盖到出场日 → 稳妥起见仍标 PENDING (理论不应发生)
        if entry_pos >= len(idx) or exit_pos >= len(idx):
            out.append({**slim, "status": "PENDING"})
            continue

        entry = float(ohlcv.iloc[entry_pos]["open"])
        exit_ = float(ohlcv.iloc[exit_pos]["close"])
        realized_ret = exit_ / entry - 1.0

        # 方向命中: 模型只发 BUY (预测跌后反弹), 涨=命中。
        # SILENT (不交易) 不计入命中率 (没下注就没对错)。
        is_buy = slim["signal"] == "BUY"
        hit = int(realized_ret > 0) if is_buy else None

        out.append({
            **slim,
            "status": "MATURE",
            "entry_price": round(entry, 2),
            "exit_price": round(exit_, 2),
            "realized_return": round(realized_ret, 6),
            "hit": hit,
        })

    return out
