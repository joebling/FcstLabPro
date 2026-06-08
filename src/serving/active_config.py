"""生产模型唯一真相源加载器 — 读取 models/production/active.yaml.

替代过去散落各脚本的硬编码 (DEFAULT_MODEL = .../e1-conservative/...)。
所有生产入口都应通过这里解析「现在用哪个模型 + 哪个 variant」。

核心保证:
  1. 唯一来源: 只认 models/production/active.yaml
  2. variant 绑定: active.yaml 声明的 strategy_variant 必须等于该模型
     manifest.json 的 deployment.variant，不一致直接 fail (Phase 2 P0)。
  3. 产物完整性: artifact_dir 下必须有 model.joblib / config.yaml。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ACTIVE_YAML = PROJECT_ROOT / "models" / "production" / "active.yaml"

# active.yaml 里被识别为「模型槽位」的顶层 key
_MODEL_ROLES = ("primary", "challenger", "candidate")

# strategy_variant → live_signal.py CLI flags 的映射 (单一定义, 消除多处重复)
VARIANT_FLAGS: dict[str, list[str]] = {
    "base": [],
    "moderate": ["--take-profit"],
    "conservative": ["--take-profit", "--regime-switch"],
}


@dataclass(frozen=True)
class ActiveModel:
    """一个已解析、已校验的生产模型槽位."""

    slot: str                 # primary / challenger / candidate
    name: str                 # 模型名 (artifact_dir basename)
    artifact_dir: Path        # 绝对路径
    role: str                 # risk_control / return_enhancement / ...
    strategy_variant: str     # base / moderate / conservative
    status: str               # live / paper / offline_only
    note: str = ""

    @property
    def model_path(self) -> Path:
        return self.artifact_dir / "model.joblib"

    @property
    def config_path(self) -> Path:
        return self.artifact_dir / "config.yaml"

    @property
    def manifest_path(self) -> Path:
        return self.artifact_dir / "manifest.json"

    @property
    def cli_flags(self) -> list[str]:
        """该 variant 对应的 live_signal.py CLI flags."""
        return VARIANT_FLAGS.get(self.strategy_variant, [])


def _parse_slot(slot: str, cfg: dict) -> ActiveModel:
    artifact_dir = PROJECT_ROOT / cfg["artifact_dir"]
    return ActiveModel(
        slot=slot,
        name=artifact_dir.name,
        artifact_dir=artifact_dir,
        role=cfg.get("role", "unknown"),
        strategy_variant=cfg.get("strategy_variant", "conservative"),
        status=cfg.get("status", "unknown"),
        note=cfg.get("note", ""),
    )


def _validate(model: ActiveModel) -> None:
    """校验产物完整性 + variant 与 manifest 一致 (variant 绑定门)."""
    if model.strategy_variant not in VARIANT_FLAGS:
        raise ValueError(
            f"[active.yaml] {model.slot}: 未知 strategy_variant "
            f"'{model.strategy_variant}'，合法值: {list(VARIANT_FLAGS)}"
        )
    if not model.model_path.exists():
        raise FileNotFoundError(
            f"[active.yaml] {model.slot} ({model.name}): 缺少 {model.model_path}"
        )
    if not model.config_path.exists():
        raise FileNotFoundError(
            f"[active.yaml] {model.slot} ({model.name}): 缺少 {model.config_path}"
        )

    # variant 绑定门: 必须与 manifest.deployment.variant 一致 (若 manifest 存在)
    if model.manifest_path.exists():
        manifest = json.loads(model.manifest_path.read_text())
        manifest_variant = manifest.get("deployment", {}).get("variant")
        if manifest_variant and manifest_variant != model.strategy_variant:
            raise ValueError(
                f"[active.yaml] {model.slot} ({model.name}): strategy_variant 冲突 — "
                f"active.yaml 写 '{model.strategy_variant}' 但 manifest.json 是 "
                f"'{manifest_variant}'。改任一方使其一致 (防止部署用错变体)。"
            )


def load_active_models(
    path: Path | None = None, *, validate: bool = True
) -> dict[str, ActiveModel]:
    """加载 active.yaml 中所有模型槽位.

    Parameters
    ----------
    path : 自定义 active.yaml 路径 (默认 models/production/active.yaml)
    validate : 是否做产物完整性 + variant 绑定校验 (默认 True)

    Returns
    -------
    dict[slot, ActiveModel]，如 {"primary": ..., "challenger": ...}
    """
    path = path or ACTIVE_YAML
    if not path.exists():
        raise FileNotFoundError(f"生产模型配置不存在: {path}")

    raw = yaml.safe_load(path.read_text()) or {}
    models: dict[str, ActiveModel] = {}
    for slot in _MODEL_ROLES:
        if slot in raw and raw[slot]:
            model = _parse_slot(slot, raw[slot])
            if validate:
                _validate(model)
            models[slot] = model

    if not models:
        raise ValueError(f"[active.yaml] 没有任何模型槽位 (期望 {_MODEL_ROLES} 之一)")
    return models


def resolve_model(
    name_or_slot: str | None = None,
    *,
    path: Path | None = None,
    validate: bool = True,
) -> ActiveModel:
    """解析单个生产模型.

    Parameters
    ----------
    name_or_slot : 可传槽位名 (primary/challenger) 或模型名 (e1-conservative)。
                   None 时默认返回 primary。
    path : 自定义 active.yaml 路径
    validate : 是否做完整性校验

    Returns
    -------
    ActiveModel
    """
    models = load_active_models(path=path, validate=validate)

    if name_or_slot is None:
        if "primary" not in models:
            raise ValueError("[active.yaml] 未定义 primary 槽位，需显式指定模型")
        return models["primary"]

    # 先按槽位名
    if name_or_slot in models:
        return models[name_or_slot]

    # 再按模型名
    for m in models.values():
        if m.name == name_or_slot:
            return m

    available = {s: m.name for s, m in models.items()}
    raise KeyError(
        f"[active.yaml] 找不到模型 '{name_or_slot}'。可用: {available}"
    )
