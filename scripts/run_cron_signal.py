#!/usr/bin/env python3
"""Cron 定时信号生成脚本.

每天 UTC 00:05 (北京时间 08:05) 自动运行。

模型清单从 models/production/active.yaml 驱动 (不再硬编码模型名/路径)。
默认跑 status=live 的槽位; 传 --include-paper 时连 paper 一起跑。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.serving import load_active_models  # noqa: E402
from src.serving.active_config import ActiveModel  # noqa: E402

# 用当前解释器, 不再硬编码 venv 绝对路径
PY = sys.executable
OUT_DIR = "/tmp/signals"


def _download_data() -> None:
    """下载最新 Binance 日线数据 (失败则回退本地)."""
    from src.data.downloader import download_binance_klines

    raw_dir = PROJECT_ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    df = download_binance_klines(symbol="BTCUSDT", interval="1d", start="2020-01-01")
    df.to_csv(raw_dir / "btc_binance_BTCUSDT_1d.csv", index=True)
    print(f"数据已更新: {len(df)} 行")


def run_model(model: ActiveModel) -> None:
    """运行单个模型的完整信号链路."""
    state_file = f"/tmp/signal_state_{model.name}.json"
    print(f"=== 运行模型: {model.slot}={model.name} (variant={model.strategy_variant}) ===")

    # 1. live_signal — 模型/配置/variant flags 全部由 active.yaml 解析
    subprocess.run(
        [PY, str(PROJECT_ROOT / "scripts/live_signal.py"),
         "--model", str(model.model_path),
         "--config", str(model.config_path),
         "--state", state_file] + model.cli_flags,
        check=True, capture_output=True,
    )

    # 2. 生成信号 JSON
    subprocess.run(
        [PY, str(PROJECT_ROOT / "scripts/build_signal_json.py"),
         "--model-dir", str(model.artifact_dir),
         "--state-file", state_file,
         "--variant", model.strategy_variant,
         "--output-dir", OUT_DIR],
        check=True, capture_output=True,
    )

    # 3. 发送邮件
    signal_files = list(Path(OUT_DIR).glob("signal_*.json"))
    if signal_files:
        subprocess.run(
            [PY, str(PROJECT_ROOT / "scripts/send_signal_email.py"), str(signal_files[0])],
            check=True, capture_output=True,
        )
        print("✅ 邮件已发送")


def main() -> int:
    parser = argparse.ArgumentParser(description="FcstLabPro Cron 信号")
    parser.add_argument("--include-paper", action="store_true",
                        help="连 status=paper 的槽位也一起跑 (默认只跑 live)")
    args = parser.parse_args()

    print("=== FcstLabPro Cron Signal ===")
    models = load_active_models()

    try:
        _download_data()
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 数据下载失败, 尝试用本地数据: {e}")

    allowed = {"live", "paper"} if args.include_paper else {"live"}
    ran = 0
    for model in models.values():
        if model.status not in allowed:
            print(f"⏭️  跳过 {model.slot}={model.name} (status={model.status})")
            continue
        try:
            run_model(model)
            ran += 1
        except Exception as e:  # noqa: BLE001
            print(f"❌ {model.name} 失败: {e}")

    print(f"✅ 全部完成 (运行 {ran} 个模型)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
