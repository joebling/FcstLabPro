#!/usr/bin/env python3
"""FcstLabPro 生产信号 pipeline — 单命令跑完「下载 → 校验 → 信号」全链路.

设计参照 EventReadiness/scripts/run_production_pipeline.py 的声明式 Stage 模式,
但因 LightGBM 推理极轻 (无 10GB 物化), 采用 **in-process** 调用而非 subprocess:
错误栈更清晰, 无需为隔离付出 `python -m` 的复杂度 (YAGNI)。

cron 只需调这一个命令:

    python scripts/run_production_pipeline.py

链路 (每个 required stage 失败即 halt, 决策 A):

  ┌────────────────────────────────────────────────────────────────┐
  │ 0  PREFLIGHT       active.yaml 解析 + 模型产物存在性校验          │
  │ 1  download_ohlcv  Binance 日线 → data/raw/...csv   (required)   │
  │ 2  download_fgi    FGI → data/external/...csv       (required)   │
  │ 3  validate_data   OHLCV + FGI freshness 强校验     (required) ★ │
  │ 4  signals         每个 active 模型 in-process 出信号 (required) │
  └────────────────────────────────────────────────────────────────┘

★ stage 3 是本 pipeline 的核心: 数据缺失 / 过期 → DataFreshnessError → halt。
  不再像旧 live_signal 那样静默 ffill stale FGI。SLA 来自 active.yaml。

研究态 (run_experiment / backtest) 不走这里, 因此 freshness gate 不会误伤回测。

Usage::

    # 标准 cron (只跑 status=live 的模型)
    python scripts/run_production_pipeline.py

    # 连 paper 模型一起跑
    python scripts/run_production_pipeline.py --include-paper

    # 看计划不执行 (validate 仍真跑, 帮你在 VPS 提前发现 stale)
    python scripts/run_production_pipeline.py --dry-run

    # 跳过下载 (假设数据已就位), 只做校验+信号 — VPS 调试用
    python scripts/run_production_pipeline.py --from-stage 3.validate_data

    # 自定义信号账本模式
    python scripts/run_production_pipeline.py --ledger-mode shadow
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OHLCV_PATH = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"
FGI_PATH = PROJECT_ROOT / "data" / "external" / "fear_greed_index.csv"

# 输出根目录: 默认跟 VPS 部署一致 (/opt/fcstlabpro), 可用 FCST_DATA_DIR 覆盖。
# 本地开发时设 FCST_DATA_DIR=/tmp/fcst 即可，不污染生产路径。
DATA_DIR = Path(os.environ.get("FCST_DATA_DIR", "/opt/fcstlabpro"))
STATE_DIR = DATA_DIR / "state"
SIGNALS_DIR = DATA_DIR / "signals"

STATUS_OK = "OK"
STATUS_FAILED = "FAILED"
STATUS_DRY = "DRY-RUN"


# ─────────────────────────────────────────────────────────────────────────
# Stage 框架
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class Stage:
    """一个 in-process pipeline stage.

    run(ctx) 返回 detail 字符串 (写进 summary)。抛异常 = stage 失败。
    required=True 的 stage 失败 → 整条 pipeline halt (决策 A)。
    """

    name: str
    run: Callable[["PipelineCtx"], str]
    required: bool = True


@dataclass
class PipelineCtx:
    """跨 stage 共享的运行上下文."""

    include_paper: bool
    ledger_mode: str
    dry_run: bool
    require_fgi: bool = True   # 由 preflight 根据模型 config 判定
    active_models: dict | None = None
    enable_llm: bool = False   # GEMINI_API_KEY 存在时由 preflight 置 True
    enable_email: bool = False  # SMTP_USER/PASS 存在时由 preflight 置 True


@dataclass
class StageResult:
    name: str
    status: str
    elapsed: float
    detail: str = ""


# ─────────────────────────────────────────────────────────────────────────
# Stage 实现
# ─────────────────────────────────────────────────────────────────────────


def _stage_download_ohlcv(ctx: PipelineCtx) -> str:
    from src.data.downloader import download_binance_klines

    df = download_binance_klines(
        symbol="BTCUSDT", interval="1d", start="2020-01-01",
        output_path=OHLCV_PATH,
    )
    return f"{len(df)} 行 → {OHLCV_PATH.name} (end={df.index[-1].date()})"


def _stage_download_fgi(ctx: PipelineCtx) -> str:
    """下载 FGI (强制刷新, 不吃 12h 缓存).

    download_fear_greed_index 内部: API 失败但有旧缓存会回退旧缓存 (不抛),
    彻底缺数据 (API 失败 + 无缓存) 才 raise。即便回退旧缓存, 过期也会在
    stage 3 validate_data 被 SLA 拦下 → halt。
    """
    from src.data.external import download_fear_greed_index

    df = download_fear_greed_index(cache=False)
    return f"{len(df)} 行 → {FGI_PATH.name} (end={df.index[-1].date()})"


def _stage_validate_data(ctx: PipelineCtx) -> str:
    """★ 核心闸门: OHLCV + FGI freshness 强校验. 任一不达标 → halt."""
    from src.serving.data_freshness import check_all

    reports = check_all(require_fgi=ctx.require_fgi)
    parts = [f"{r.source}: stale={r.stale_days}d/SLA={r.sla_days}d ✅" for r in reports]
    if not ctx.require_fgi:
        parts.append("fgi: 跳过 (模型不依赖)")
    return "; ".join(parts)


def _stage_signals(ctx: PipelineCtx) -> str:
    """对每个 active 模型: 信号 → JSON → (LLM) → (邮件).

    JSON/LLM/邮件 是输出侧 (required=False 语义): 单个环节失败不应让整条
    pipeline halt (信号本身已生成)。但 run_for_model 本身 (拉数/特征/推理)
    失败会抛出 → stage FAILED → halt。
    """
    from src.serving import load_active_models

    models = ctx.active_models or load_active_models()
    allowed = {"live", "paper"} if ctx.include_paper else {"live"}

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)

    ran: list[str] = []
    for model in models.values():
        if model.status not in allowed:
            continue
        ran.append(_run_one_model(model, ctx))

    if not ran:
        raise RuntimeError(
            f"没有匹配 status∈{allowed} 的模型 — 检查 active.yaml 与 --include-paper"
        )
    return ", ".join(ran)


def _run_one_model(model, ctx: PipelineCtx) -> str:
    """单模型完整链路. 返回 'name=SIGNAL[+json][+llm][+mail]' 摘要."""
    from scripts.live_signal import run_for_model

    state_path = STATE_DIR / f"{model.name}_state.json"
    out_dir = SIGNALS_DIR / model.name
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. 信号 (推理失败会抛 → stage FAILED → halt)
    signal, _meta = run_for_model(
        model, state_path=state_path,
        ledger_mode="dry-run" if ctx.dry_run else ctx.ledger_mode,
    )
    tags = [signal]

    # 2. JSON (输出侧, 失败不 halt)
    signal_json = _try_build_json(model, state_path, out_dir, tags)

    # 3. LLM (可选, 失败不 halt)
    if signal_json and ctx.enable_llm:
        _try_llm(signal_json, tags)

    # 4. 邮件 (可选, 失败不 halt; dry-run 不发)
    if signal_json and ctx.enable_email and not ctx.dry_run:
        _try_email(signal_json, tags)

    return f"{model.name}={'+'.join(tags)}"


def _try_build_json(model, state_path: Path, out_dir: Path, tags: list[str]):
    """生成信号 JSON. 返回 Path 或 None."""
    try:
        from scripts.build_signal_json import build_signal_json

        p = build_signal_json(
            model_dir=model.artifact_dir,
            state_file=state_path,
            variant=model.strategy_variant,
            output_dir=out_dir,
            data_path=OHLCV_PATH,
        )
        if p:
            tags.append("json")
        return p
    except Exception as e:  # noqa: BLE001
        print(f"⚠️  {model.name}: build_signal_json 失败 (不阻断): {e}")
        return None


def _try_llm(signal_json: Path, tags: list[str]) -> None:
    try:
        from scripts.enrich_llm_analysis import main as enrich_llm

        enrich_llm(str(signal_json))
        tags.append("llm")
    except Exception as e:  # noqa: BLE001
        print(f"⚠️  LLM 分析失败 (不阻断): {e}")


def _try_email(signal_json: Path, tags: list[str]) -> None:
    try:
        from scripts.send_signal_email import send_email

        if send_email(str(signal_json)):
            tags.append("mail")
    except Exception as e:  # noqa: BLE001
        print(f"⚠️  邮件发送失败 (不阻断): {e}")


STAGES: list[Stage] = [
    Stage("1.download_ohlcv", _stage_download_ohlcv),
    Stage("2.download_fgi", _stage_download_fgi),
    Stage("3.validate_data", _stage_validate_data),
    Stage("4.signals", _stage_signals),
]


# ─────────────────────────────────────────────────────────────────────────
# Preflight
# ─────────────────────────────────────────────────────────────────────────


def preflight(args: argparse.Namespace) -> PipelineCtx:
    """解析 active.yaml + 判定是否需要 FGI. 产物缺失直接 fail (active_config 内置校验)."""
    import yaml

    from src.serving import load_active_models

    models = load_active_models()  # 内部已校验 model.joblib / config.yaml / variant

    allowed = {"live", "paper"} if args.include_paper else {"live"}
    require_fgi = False
    for m in models.values():
        if m.status not in allowed:
            continue
        cfg = yaml.safe_load(m.config_path.read_text()) or {}
        sets = (cfg.get("features", {}) or {}).get("sets", []) or []
        if "external_fgi" in sets or "external" in sets:
            require_fgi = True

    slots = [f"{s}={m.name}({m.status})" for s, m in models.items()]

    # LLM / 邮件: 凭据存在才启用 (跟 VPS .sh 的环境变量门控一致)
    enable_llm = bool(os.environ.get("GEMINI_API_KEY"))
    enable_email = bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"))

    bar = "─" * 72
    print(bar)
    print(f"[preflight] active 模型槽位 : {slots}")
    print(f"[preflight] 跑哪些状态     : {sorted(allowed)}")
    print(f"[preflight] 依赖 FGI?      : {require_fgi}")
    print(f"[preflight] LLM / 邮件     : llm={enable_llm}, email={enable_email}")
    print(f"[preflight] 输出目录     : {DATA_DIR}")
    print(f"[preflight] ledger-mode    : {'dry-run' if args.dry_run else args.ledger_mode}")
    print(bar)

    return PipelineCtx(
        include_paper=args.include_paper,
        ledger_mode=args.ledger_mode,
        dry_run=args.dry_run,
        require_fgi=require_fgi,
        active_models=models,
        enable_llm=enable_llm,
        enable_email=enable_email,
    )


# ─────────────────────────────────────────────────────────────────────────
# 执行 + summary
# ─────────────────────────────────────────────────────────────────────────


def _select_stages(args: argparse.Namespace) -> list[Stage]:
    stages = list(STAGES)
    if args.only_stage:
        stages = [s for s in stages if s.name == args.only_stage]
        if not stages:
            raise SystemExit(
                f"--only-stage={args.only_stage!r} 无匹配; 可用: {[s.name for s in STAGES]}"
            )
    elif args.from_stage:
        names = [s.name for s in STAGES]
        if args.from_stage not in names:
            raise SystemExit(
                f"--from-stage={args.from_stage!r} 无匹配; 可用: {names}"
            )
        cutoff = names.index(args.from_stage)
        keep = set(names[cutoff:])
        stages = [s for s in stages if s.name in keep]
    return stages


def _run_stage(stage: Stage, ctx: PipelineCtx, dry_run: bool) -> StageResult:
    # dry-run 仍真跑 validate_data (只读校验, 帮你在 VPS 提前发现 stale)
    if dry_run and stage.name != "3.validate_data":
        return StageResult(stage.name, STATUS_DRY, 0.0, "计划执行 (dry-run 跳过)")

    print(f"\n[{stage.name}] 开始...")
    t0 = time.time()
    try:
        detail = stage.run(ctx)
        return StageResult(stage.name, STATUS_OK, time.time() - t0, detail)
    except Exception as e:  # noqa: BLE001
        return StageResult(
            stage.name, STATUS_FAILED, time.time() - t0, f"{type(e).__name__}: {e}"
        )


def print_summary(results: list[StageResult]) -> None:
    print("\n" + "═" * 72)
    print(f"{'STAGE':<18} {'STATUS':<10} {'ELAPSED':>9}   DETAIL")
    print("─" * 72)
    total = 0.0
    for r in results:
        total += r.elapsed
        print(f"{r.name:<18} {r.status:<10} {r.elapsed:>7.1f}s   {r.detail}")
    print("─" * 72)
    print(f"{'TOTAL':<18} {'':<10} {total:>7.1f}s")
    print("═" * 72)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--include-paper", action="store_true",
                    help="连 status=paper 的模型一起跑 (默认只跑 live)")
    ap.add_argument("--ledger-mode", default="live",
                    choices=["live", "shadow", "dry-run"],
                    help="信号账本写入模式 (默认 live)")
    ap.add_argument("--dry-run", action="store_true",
                    help="打印计划, 不下载/不出信号 (但仍真跑 validate_data 只读校验)")
    ap.add_argument("--only-stage", default=None,
                    help="只跑指定 stage (调试用), 如 '3.validate_data'")
    ap.add_argument("--from-stage", default=None,
                    help="从指定 stage 开始跑 (跳过下载等), 如 '3.validate_data'")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    print("=== FcstLabPro 生产信号 Pipeline ===")
    ctx = preflight(args)
    stages = _select_stages(args)

    results: list[StageResult] = []
    fatal = False
    for stage in stages:
        result = _run_stage(stage, ctx, args.dry_run)
        results.append(result)
        if result.status == STATUS_FAILED and stage.required:
            fatal = True
            print(f"\n[pipeline] FATAL — stage {stage.name} 失败, halt。\n  → {result.detail}")
            break

    print_summary(results)
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
