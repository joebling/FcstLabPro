"""测试信号 JSON 的模型元信息解析。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.build_signal_json import _extract_version, _parse_model_info


def test_extract_version_supports_prefix_and_embedded_ids():
    """实验版本可从 v0601_xxx 或 xxx_v0601_xxx 提取。"""
    assert _extract_version("v0601_E20c_prune_core_run1") == "v0601"
    assert _extract_version("weekly_bear_v0305_E1_decontam") == "v0305"
    assert _extract_version("legacy_without_version") == "v0305"


def test_parse_model_info_keeps_raw_name_and_v0601():
    """E20c 晋升后邮件标题应显示真实模型名与 v0601。"""
    manifest = {
        "name": "e20c-conservative-prune",
        "source_experiment": {"id": "v0601_E20c_prune_core_run1"},
        "model": {"type": "lightgbm"},
        "strategy": {"label": "directional_filtered"},
        "features": {"count": 28},
        "metrics": {
            "classification": {"cohen_kappa": 0.4448},
            "pnl": {"策略(止盈+regime)": {"cagr": 0.188, "max_drawdown": -0.127, "profit_factor": 1.397, "sharpe": 0.923}},
        },
    }

    info = _parse_model_info(manifest, "conservative")

    assert info["name"] == "E20C Conservative Prune"
    assert info["raw_name"] == "e20c-conservative-prune"
    assert info["version"] == "v0601"
    assert info["features"] == 28
    assert info["backtest"]["cagr"] == "18.8%"


def run_all() -> bool:
    """允许 `python tests/test_build_signal_json.py` 直接执行。"""
    tests = [
        test_extract_version_supports_prefix_and_embedded_ids,
        test_parse_model_info_keeps_raw_name_and_v0601,
    ]
    for test in tests:
        test()
        print(f"✅ {test.__name__}")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_all() else 1)
