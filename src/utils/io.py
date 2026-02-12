"""文件读写工具."""

import json
from pathlib import Path

import pandas as pd
import yaml


def read_json(path: str | Path) -> dict:
    """读取 JSON 文件."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(data: dict, path: str | Path) -> None:
    """写入 JSON 文件."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def read_yaml(path: str | Path) -> dict:
    """读取 YAML 文件."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_yaml(data: dict, path: str | Path) -> None:
    """写入 YAML 文件."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def read_csv(path: str | Path, **kwargs) -> pd.DataFrame:
    """读取 CSV 文件."""
    return pd.read_csv(path, **kwargs)


def write_csv(df: pd.DataFrame, path: str | Path, **kwargs) -> None:
    """写入 CSV 文件."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, **kwargs)
