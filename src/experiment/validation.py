"""实验配置硬校验 — 把机构手册的「软规则」变成「代码硬门」.

对应 docs/reviews/cr_0529 §4 和 CLAUDE.md §2 的实验核心规范。

设计取舍: 用纯函数校验, 不引入 Pydantic。
  - 不增加生产依赖 (lockfile 已锁定, 加依赖要重验复现性)
  - 只需 fail-fast 校验, 不需要 ORM 式建模 (YAGNI)

强制规则 (违反 → ConfigValidationError):
  1. Non-overlapping: evaluation.step == label.T (机构手册 §2.1)
  2. Purge gap: evaluation.purge_gap >= label.T (防标签泄露)
  3. Walk-forward: evaluation.method == "walk_forward" (禁 train-once-predict-all)
  4. Seed 存在 (复现性前提)
  5. label.strategy 已注册
  6. model.type 非空
  7. data.path 存在
  8. features.sets 非空
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class ConfigValidationError(ValueError):
    """配置违反实验核心规范时抛出."""


def _require(cond: bool, msg: str, errors: list[str]) -> None:
    if not cond:
        errors.append(msg)


def validate_experiment_config(config: dict, *, strict_data: bool = True) -> None:
    """校验实验配置, 违规则抛 ConfigValidationError (汇总所有问题).

    Parameters
    ----------
    config : 合并后的完整配置 dict
    strict_data : True 时校验 data.path 文件存在 (单测/dry-run 可设 False)
    """
    errors: list[str] = []

    label = config.get("label", {}) or {}
    evaluation = config.get("evaluation", {}) or {}
    data = config.get("data", {}) or {}
    features = config.get("features", {}) or {}
    model = config.get("model", {}) or {}

    # ── 规则 1: Non-overlapping (step == T) ──
    T = label.get("T")
    step = evaluation.get("step")
    if T is None:
        errors.append("label.T 缺失 (预测窗口必填)")
    if step is None:
        errors.append("evaluation.step 缺失 (采样步长必填)")
    if T is not None and step is not None:
        _require(
            step == T,
            f"❌ Non-overlapping 违规: evaluation.step ({step}) 必须 == label.T ({T})。"
            f" 机构手册 §2.1: 实验样本必须每 T 天采样一次, 严禁重叠标签。",
            errors,
        )

    # ── 规则 2: Purge gap >= T ──
    purge_gap = evaluation.get("purge_gap")
    if purge_gap is None:
        errors.append("evaluation.purge_gap 缺失 (防标签泄露必填)")
    elif T is not None:
        _require(
            purge_gap >= T,
            f"❌ Purge gap 违规: evaluation.purge_gap ({purge_gap}) 必须 >= label.T ({T})，"
            f" 否则训练集会泄露未来标签。",
            errors,
        )

    # ── 规则 3: Walk-forward ──
    method = evaluation.get("method")
    _require(
        method == "walk_forward",
        f"❌ 验证方法违规: evaluation.method ('{method}') 必须为 'walk_forward'。"
        f" 机构手册 §2.2: 严禁 train-once-predict-all 伪 OOS。",
        errors,
    )

    # ── 规则 4: Seed ──
    _require(
        config.get("seed") is not None,
        "❌ seed 缺失: 复现性前提 (机构手册 §5.3 要求 seed=42)。",
        errors,
    )

    # ── 规则 5: label.strategy 已注册 ──
    strategy = label.get("strategy")
    if not strategy:
        errors.append("label.strategy 缺失")
    else:
        _validate_label_registered(strategy, errors)

    # ── 规则 6: model.type ──
    _require(bool(model.get("type")), "model.type 缺失", errors)

    # ── 规则 7: data.path ──
    path = data.get("path")
    if not path:
        errors.append("data.path 缺失")
    elif strict_data:
        abs_path = PROJECT_ROOT / path
        _require(
            abs_path.exists(),
            f"data.path 文件不存在: {path}",
            errors,
        )

    # ── 规则 8: features.sets 非空 ──
    sets = features.get("sets")
    _require(
        bool(sets) and isinstance(sets, list),
        "features.sets 缺失或为空 (至少一个特征集)",
        errors,
    )

    if errors:
        bullet = "\n  - ".join(errors)
        raise ConfigValidationError(
            f"配置校验失败 ({len(errors)} 项):\n  - {bullet}"
        )

    logger.info("✅ 配置校验通过 (Non-overlapping / purge / walk-forward / seed 全部合规)")


def _validate_label_registered(strategy: str, errors: list[str]) -> None:
    """检查标签策略是否在注册表中 (容错: 注册表导入失败则跳过)."""
    try:
        # 触发所有标签策略注册
        import src.labels.reversal  # noqa: F401
        import src.labels.directional  # noqa: F401
        import src.labels.triple_barrier  # noqa: F401
        import src.labels.return_rate  # noqa: F401
        import src.labels.pump_dump  # noqa: F401
        import src.labels.triple_barrier_simple  # noqa: F401
        import src.labels.dip_recovery_v2  # noqa: F401
        import src.labels.directional_filtered  # noqa: F401
        try:
            import src.labels.touch_filtered  # noqa: F401
        except ImportError:
            pass
        from src.labels.registry import list_label_strategies

        registered = list_label_strategies()
        if strategy not in registered:
            errors.append(
                f"label.strategy '{strategy}' 未注册。已注册: {sorted(registered)}"
            )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"标签注册表校验跳过 (导入失败): {e}")
