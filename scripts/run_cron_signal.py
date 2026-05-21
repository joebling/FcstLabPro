#!/usr/bin/env python3
"""Cron 定时信号生成脚本.

每天 UTC 00:05 (北京时间 08:05) 自动运行.
"""

import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path("/Users/qiubling/Desktop/projects/FcstLabPro")
venv_python = "/Users/qiubling/Desktop/projects/FcstLabPro/venv_py310/bin/python"

MODELS = [
    ("e1-conservative", "conservative"),
    ("e8-touch", "conservative"),
]

OUT_DIR = "/tmp/signals"

def run_model(model_name: str, variant: str):
    """运行单个模型."""
    model_dir = PROJECT_ROOT / f"models/production/{model_name}"
    state_file = f"/tmp/signal_state_{model_name}.json"

    # 构建 SIGNAL_FLAGS
    if variant == "conservative":
        signal_flags = ["--take-profit", "--regime-switch"]
    elif variant == "moderate":
        signal_flags = ["--take-profit"]
    else:
        signal_flags = []

    print(f"=== 运行模型: {model_name} ===")

    # 1. 下载最新数据
    subprocess.run([
        str(venv_python), "-c", """
import sys
sys.path.insert(0, '/Users/qiubling/Desktop/projects/FcstLabPro')
from src.data.downloader import download_binance_klines
from pathlib import Path
Path('/Users/qiubling/Desktop/projects/FcstLabPro/data/raw').mkdir(parents=True, exist_ok=True)
df = download_binance_klines(symbol='BTCUSDT', interval='1d', start='2020-01-01')
df.to_csv('/Users/qiubling/Desktop/projects/FcstLabPro/data/raw/btc_binance_BTCUSDT_1d.csv', index=True)
print(f'数据已更新: {len(df)} 行')
"""
    ], check=True, capture_output=True)

    # 2. 运行 live_signal.py
    cmd = [
        str(venv_python),
        str(PROJECT_ROOT / "scripts/live_signal.py"),
        "--model", str(model_dir / "model.joblib"),
        "--config", str(model_dir / "config.yaml"),
        "--state", state_file,
    ] + signal_flags

    subprocess.run(cmd, check=True, capture_output=True)

    # 3. 生成信号 JSON
    subprocess.run([
        str(venv_python),
        str(PROJECT_ROOT / "scripts/build_signal_json.py"),
        "--model-dir", str(model_dir),
        "--state-file", state_file,
        "--variant", variant,
        "--output-dir", OUT_DIR,
    ], check=True, capture_output=True)

    # 4. 发送邮件
    signal_file = list(Path(OUT_DIR).glob("signal_*.json"))
    if signal_file:
        subprocess.run([
            str(venv_python),
            str(PROJECT_ROOT / "scripts/send_signal_email.py"),
            str(signal_file[0]),
        ], check=True, capture_output=True)
        print(f"✅ 邮件已发送")

if __name__ == "__main__":
    print("=== FcstLabPro Cron Signal ===")

    for model_name, variant in MODELS:
        try:
            run_model(model_name, variant)
        except Exception as e:
            print(f"❌ {model_name} 失败: {e}")

    print("✅ 全部完成")