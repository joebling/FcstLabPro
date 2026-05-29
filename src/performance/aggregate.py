"""批次聚合 + 滚动指标.

对标 RiskDetect sellers.py 的 batches() + auc_live(): 把回填明细聚合到
score_date 批次级别, 算命中率/实现收益/滚动 IC。dashboard 经 service 层
实时调用 (无中间文件产物)。
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone

from src.performance.backfill import backfill_outcomes


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank IC (Spearman) — 复用机构手册 §2.3 的口径. 无 scipy 依赖."""
    n = len(xs)
    if n < 3:
        return None

    def _rank(vals: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: vals[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0  # 1-based 平均秩 (处理并列)
            for k in range(i, j + 1):
                ranks[order[k]] = avg
            i = j + 1
        return ranks

    rx, ry = _rank(xs), _rank(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def build_batches(model_name: str, *, label_T: int, ohlcv=None,
                  today=None, limit: int = 30) -> list[dict]:
    """聚合到批次级 (本项目每日每模型通常 1 条, 仍按 score_date 分组以备扩展)."""
    rows = backfill_outcomes(model_name, label_T=label_T, ohlcv=ohlcv, today=today)

    by_date: dict[str, list[dict]] = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(r)

    batches = []
    for d in sorted(by_date, reverse=True)[:limit]:
        recs = by_date[d]
        mature = [r for r in recs if r["status"] == "MATURE"]
        bets = [r for r in mature if r["hit"] is not None]  # 只有 BUY 算命中
        n_buy = sum(1 for r in recs if r["signal"] == "BUY")

        hit_rate = round(100 * sum(r["hit"] for r in bets) / len(bets), 1) if bets else None
        avg_ret = round(100 * statistics.mean(r["realized_return"] for r in mature), 2) if mature else None

        batches.append({
            "score_date": d,
            "n_signals": len(recs),
            "n_buy": n_buy,
            "n_silent": len(recs) - n_buy,
            "status": "MATURE" if mature else "PENDING",
            "hit_rate": hit_rate,
            "avg_realized_return": avg_ret,
            "model_hash": recs[0].get("model_hash", ""),
        })
    return batches


def build_summary(model_name: str, *, label_T: int, ohlcv=None, today=None) -> dict:
    """滚动汇总: 整体命中率 / 平均实现收益 / Rank IC (BUY 方向 vs 实现收益)."""
    rows = backfill_outcomes(model_name, label_T=label_T, ohlcv=ohlcv, today=today)
    mature = [r for r in rows if r["status"] == "MATURE"]
    bets = [r for r in mature if r["hit"] is not None]

    # Rank IC: 用 BUY 下注 (1) 与实现收益的秩相关. 信号是二值, IC 衡量
    # "发 BUY 的日子是否确实对应更高的未来收益"。
    signal_num = [1.0 if r["signal"] == "BUY" else 0.0 for r in mature]
    returns = [r["realized_return"] for r in mature]
    rank_ic = _spearman(signal_num, returns)

    return {
        "model_name": model_name,
        "n_total": len(rows),
        "n_mature": len(mature),
        "n_pending": len(rows) - len(mature),
        "n_bets": len(bets),
        "hit_rate": round(100 * sum(r["hit"] for r in bets) / len(bets), 1) if bets else None,
        "avg_realized_return": round(100 * statistics.mean(returns), 2) if mature else None,
        "rank_ic": round(rank_ic, 4) if rank_ic is not None else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }



