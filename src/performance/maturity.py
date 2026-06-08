"""标签成熟度门控 — 决定一条信号是否"到结果了".

⚠️ 单一真相源: 成熟滞后从 model config 的 label.T 推导, 任何需要
   "标签成熟"概念的地方 (回填/聚合/报告) 必须 import 这里, 不许各自
   +21 +22 —— drift here = 各页面数字静默不一致。
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import yaml

# t_close 出信号 → t+1_open 执行, 标签窗口结束后才算"结果落定"。
# 公式: lag = label.T + EXEC_BUFFER_DAYS
EXEC_BUFFER_DAYS = 1


def maturity_lag_days(model_config: dict) -> int:
    """从 model config 推导成熟滞后天数 (= label.T + 执行 buffer)."""
    T = model_config["label"]["T"]
    return int(T) + EXEC_BUFFER_DAYS


def maturity_lag_from_config_path(config_path) -> int:
    """便捷: 直接给 config.yaml 路径."""
    cfg = yaml.safe_load(open(config_path).read()) or {}
    return maturity_lag_days(cfg)


def _as_date(d: str | date) -> date:
    if isinstance(d, date):
        return d
    return datetime.strptime(d, "%Y-%m-%d").date()


def is_mature(score_date: str | date, lag_days: int, *, today: date | None = None) -> bool:
    """该批次是否已成熟 (到了可评判对错的时间).

    成熟条件: score_date + lag_days <= today。
    """
    today = today or datetime.now(timezone.utc).date()
    sd = _as_date(score_date)
    return (today - sd).days >= lag_days
