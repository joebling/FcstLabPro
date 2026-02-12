"""实验配置加载与合并模块."""

import copy
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BASE_CONFIG_PATH = PROJECT_ROOT / "configs" / "base.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典, override 优先."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_base_config() -> dict:
    """加载基础默认配置."""
    if not BASE_CONFIG_PATH.exists():
        logger.warning(f"基础配置不存在: {BASE_CONFIG_PATH}, 使用空配置")
        return {}
    with open(BASE_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_experiment_config(config_path: str | Path) -> dict:
    """加载实验配置（自动与 base.yaml 合并）.

    Parameters
    ----------
    config_path : str | Path
        实验配置 YAML 文件路径

    Returns
    -------
    dict
        合并后的完整配置
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"实验配置不存在: {config_path}")

    base = load_base_config()
    with open(config_path, encoding="utf-8") as f:
        exp = yaml.safe_load(f) or {}

    merged = _deep_merge(base, exp)
    logger.info(f"配置已加载并合并: {config_path.name}")
    return merged


def apply_overrides(config: dict, overrides: list[str]) -> dict:
    """应用命令行覆盖参数.

    Parameters
    ----------
    config : dict
        当前配置
    overrides : list[str]
        覆盖参数列表, 如 ["label.T=21", "label.X=0.10"]

    Returns
    -------
    dict
        应用覆盖后的配置
    """
    config = copy.deepcopy(config)
    for item in overrides:
        if "=" not in item:
            logger.warning(f"无效的覆盖参数格式: {item}, 应为 key.path=value")
            continue

        key_path, value_str = item.split("=", 1)
        keys = key_path.strip().split(".")

        # 自动类型推断
        value: Any
        try:
            value = int(value_str)
        except ValueError:
            try:
                value = float(value_str)
            except ValueError:
                if value_str.lower() in ("true", "false"):
                    value = value_str.lower() == "true"
                elif value_str.lower() == "null":
                    value = None
                else:
                    value = value_str

        # 深度设置
        d = config
        for k in keys[:-1]:
            if k not in d:
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value
        logger.info(f"配置覆盖: {key_path} = {value}")

    return config


def save_config(config: dict, path: str | Path) -> None:
    """保存配置到 YAML 文件."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    logger.info(f"配置已保存: {path}")
