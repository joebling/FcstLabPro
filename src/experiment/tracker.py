"""实验追踪器 — 管理实验 ID、注册表、元信息."""

import json
import hashlib
import logging
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"
REGISTRY_PATH = EXPERIMENTS_DIR / "registry.json"


def generate_experiment_id(config: dict) -> str:
    """根据配置生成唯一实验 ID.

    格式: {name}_{YYYYMMDD}_{HHmmss}_{hash6}
    """
    name = config.get("experiment", {}).get("name", "unnamed")
    # 用配置内容的 hash 来保证唯一性
    config_str = json.dumps(config, sort_keys=True, default=str)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    hash6 = hashlib.md5((config_str + ts).encode()).hexdigest()[:6]
    exp_id = f"{name}_{ts}_{hash6}"
    return exp_id


def get_git_info() -> dict:
    """获取当前 git 信息."""
    info = {"commit": "unknown", "branch": "unknown", "dirty": True}
    try:
        info["commit"] = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()

        info["branch"] = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=PROJECT_ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()

        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
        info["dirty"] = len(status) > 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("无法获取 git 信息")
    return info


def create_experiment_dir(experiment_id: str) -> Path:
    """创建实验目录."""
    exp_dir = EXPERIMENTS_DIR / experiment_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"实验目录已创建: {exp_dir}")
    return exp_dir


def build_meta(config: dict, experiment_id: str) -> dict:
    """构建实验元信息."""
    return {
        "experiment_id": experiment_id,
        "name": config.get("experiment", {}).get("name", ""),
        "description": config.get("experiment", {}).get("description", ""),
        "tags": config.get("experiment", {}).get("tags", []),
        "created_at": datetime.now().isoformat(),
        "git": get_git_info(),
        "seed": config.get("seed", None),
        "status": "running",
        "duration_seconds": None,
    }


def save_meta(meta: dict, exp_dir: Path) -> None:
    """保存元信息."""
    path = exp_dir / "meta.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, default=str)


def update_registry(experiment_id: str, meta: dict) -> None:
    """更新实验注册表."""
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)

    registry = []
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            registry = json.load(f)

    # 添加摘要条目
    entry = {
        "experiment_id": experiment_id,
        "name": meta.get("name", ""),
        "tags": meta.get("tags", []),
        "created_at": meta.get("created_at", ""),
        "status": meta.get("status", "unknown"),
        "git_commit": meta.get("git", {}).get("commit", "unknown"),
    }

    # 如果已存在则更新
    for i, e in enumerate(registry):
        if e["experiment_id"] == experiment_id:
            registry[i] = entry
            break
    else:
        registry.append(entry)

    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"注册表已更新, 当前共 {len(registry)} 个实验")


def list_experiments() -> list[dict]:
    """列出所有已注册的实验."""
    if not REGISTRY_PATH.exists():
        return []
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)
