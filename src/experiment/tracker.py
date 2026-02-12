"""实验追踪器 — 管理实验 ID、注册表、元信息."""

import json
import hashlib
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"
REGISTRY_PATH = EXPERIMENTS_DIR / "registry.json"
ARCHIVE_DIR = PROJECT_ROOT / "experiments_archive"


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


def create_experiment_dir(experiment_id: str, category: str = "default") -> Path:
    """创建实验目录（按 category 分级）.

    目录结构: experiments/{category}/{experiment_id}/
    """
    exp_dir = EXPERIMENTS_DIR / category / experiment_id
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
        "category": config.get("experiment", {}).get("category", "default"),
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
    """更新实验注册表（含汇总指标和耗时）."""
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)

    registry = _load_registry()

    # 添加摘要条目（增强版：含指标和耗时）
    entry = {
        "experiment_id": experiment_id,
        "name": meta.get("name", ""),
        "description": meta.get("description", ""),
        "category": meta.get("category", "default"),
        "tags": meta.get("tags", []),
        "created_at": meta.get("created_at", ""),
        "status": meta.get("status", "unknown"),
        "duration_seconds": meta.get("duration_seconds"),
        "git_commit": meta.get("git", {}).get("commit", "unknown"),
        "git_branch": meta.get("git", {}).get("branch", "unknown"),
        "git_dirty": meta.get("git", {}).get("dirty", True),
        "seed": meta.get("seed"),
        "aggregate_metrics": meta.get("aggregate_metrics", {}),
        "error": meta.get("error"),
    }

    # 如果已存在则更新
    for i, e in enumerate(registry):
        if e["experiment_id"] == experiment_id:
            registry[i] = entry
            break
    else:
        registry.append(entry)

    _save_registry(registry)
    logger.info(f"注册表已更新, 当前共 {len(registry)} 个实验")


def _load_registry() -> list[dict]:
    """内部：加载注册表."""
    if not REGISTRY_PATH.exists():
        return []
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_registry(registry: list[dict]) -> None:
    """内部：保存注册表."""
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2, default=str)


def list_experiments() -> list[dict]:
    """列出所有已注册的实验."""
    return _load_registry()


def filter_experiments(
    status: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    name_contains: str | None = None,
    sort_by: str | None = None,
    ascending: bool = True,
    top_n: int | None = None,
) -> list[dict]:
    """按条件筛选和排序实验.

    Parameters
    ----------
    status : 按状态筛选 (completed / failed / running)
    category : 按大类筛选 (baseline / feature_study / param_tuning / ...)
    tags : 必须包含所有指定标签
    name_contains : 名称包含指定子串
    sort_by : 排序字段，支持 'created_at', 'duration_seconds',
              或指标名如 'accuracy', 'f1_macro' 等
    ascending : 排序方向
    top_n : 取前 N 个
    """
    registry = _load_registry()

    if status:
        registry = [e for e in registry if e.get("status") == status]

    if category:
        registry = [e for e in registry if e.get("category") == category]

    if tags:
        registry = [e for e in registry
                     if all(t in e.get("tags", []) for t in tags)]

    if name_contains:
        registry = [e for e in registry
                     if name_contains.lower() in e.get("name", "").lower()
                     or name_contains.lower() in e.get("experiment_id", "").lower()]

    if sort_by:
        def _sort_key(entry):
            # 先尝试顶层字段
            if sort_by in entry:
                val = entry[sort_by]
                return val if val is not None else (0 if ascending else float('inf'))
            # 再尝试 aggregate_metrics 内的字段
            metrics = entry.get("aggregate_metrics", {})
            val = metrics.get(sort_by)
            return val if val is not None else (0 if ascending else float('inf'))

        registry.sort(key=_sort_key, reverse=not ascending)

    if top_n:
        registry = registry[:top_n]

    return registry


def _find_experiment_dir(experiment_id: str) -> Path | None:
    """在 experiments/ 下递归查找实验目录."""
    # 先检查直接子目录（旧格式兼容）
    d = EXPERIMENTS_DIR / experiment_id
    if d.exists() and d.is_dir():
        return d
    # 再检查分类子目录
    for category_dir in EXPERIMENTS_DIR.iterdir():
        if category_dir.is_dir() and not category_dir.name.startswith("."):
            candidate = category_dir / experiment_id
            if candidate.exists() and candidate.is_dir():
                return candidate
    # 归档目录
    if ARCHIVE_DIR.exists():
        d = ARCHIVE_DIR / experiment_id
        if d.exists():
            return d
        for category_dir in ARCHIVE_DIR.iterdir():
            if category_dir.is_dir():
                candidate = category_dir / experiment_id
                if candidate.exists() and candidate.is_dir():
                    return candidate
    return None


def delete_experiment(experiment_id: str, delete_files: bool = True) -> bool:
    """删除实验（从注册表移除，并可选删除目录）.

    Returns True if found and deleted.
    """
    registry = _load_registry()
    new_registry = [e for e in registry if e["experiment_id"] != experiment_id]

    if len(new_registry) == len(registry):
        logger.warning(f"实验 '{experiment_id}' 不在注册表中")
        return False

    _save_registry(new_registry)

    if delete_files:
        exp_dir = _find_experiment_dir(experiment_id)
        if exp_dir and exp_dir.exists():
            shutil.rmtree(exp_dir)
            logger.info(f"已删除实验目录: {exp_dir}")

    logger.info(f"已从注册表移除实验: {experiment_id}")
    return True


def cleanup_failed(delete_files: bool = True) -> list[str]:
    """清理所有失败的实验.

    Returns list of deleted experiment IDs.
    """
    registry = _load_registry()
    failed = [e for e in registry if e.get("status") == "failed"]
    deleted_ids = []

    for entry in failed:
        eid = entry["experiment_id"]
        delete_experiment(eid, delete_files=delete_files)
        deleted_ids.append(eid)

    logger.info(f"已清理 {len(deleted_ids)} 个失败实验")
    return deleted_ids


def archive_experiments(
    experiment_ids: list[str] | None = None,
    before_date: str | None = None,
    status: str | None = None,
) -> list[str]:
    """归档实验（移到 experiments_archive/ 目录）.

    Parameters
    ----------
    experiment_ids : 指定要归档的实验 ID
    before_date : 归档此日期之前的实验 (ISO 格式, 如 '2026-01-01')
    status : 归档指定状态的实验
    """
    registry = _load_registry()
    to_archive = []

    for entry in registry:
        eid = entry["experiment_id"]
        if experiment_ids and eid in experiment_ids:
            to_archive.append(entry)
        elif before_date and entry.get("created_at", "") < before_date:
            to_archive.append(entry)
        elif status and entry.get("status") == status:
            to_archive.append(entry)

    archived_ids = []
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    for entry in to_archive:
        eid = entry["experiment_id"]
        src = EXPERIMENTS_DIR / eid
        dst = ARCHIVE_DIR / eid
        if src.exists():
            shutil.move(str(src), str(dst))
            logger.info(f"已归档: {eid} -> {dst}")
        archived_ids.append(eid)

    # 从注册表移除已归档的，保存到归档注册表
    archived_registry_path = ARCHIVE_DIR / "registry_archived.json"
    archived_registry = []
    if archived_registry_path.exists():
        with open(archived_registry_path, encoding="utf-8") as f:
            archived_registry = json.load(f)
    archived_registry.extend(to_archive)
    with open(archived_registry_path, "w", encoding="utf-8") as f:
        json.dump(archived_registry, f, ensure_ascii=False, indent=2, default=str)

    # 从主注册表删除
    new_registry = [e for e in registry if e["experiment_id"] not in archived_ids]
    _save_registry(new_registry)

    logger.info(f"已归档 {len(archived_ids)} 个实验")
    return archived_ids


def get_experiment_summary(experiment_id: str) -> dict | None:
    """获取单个实验的完整摘要（从 meta.json 读取）."""
    exp_dir = _find_experiment_dir(experiment_id)
    if exp_dir is None:
        return None
    meta_path = exp_dir / "meta.json"
    if not meta_path.exists():
        return None
    with open(meta_path, encoding="utf-8") as f:
        return json.load(f)


def get_experiment_dir(experiment_id: str) -> Path | None:
    """获取实验目录路径."""
    return _find_experiment_dir(experiment_id)


def get_best_experiment(
    metric: str = "accuracy",
    status: str = "completed",
    higher_is_better: bool = True,
) -> dict | None:
    """获取指定指标最优的实验."""
    results = filter_experiments(
        status=status,
        sort_by=metric,
        ascending=not higher_is_better,
        top_n=1,
    )
    return results[0] if results else None
