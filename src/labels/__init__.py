"""标签生成模块.

提供多种标签策略:
- reversal: 反转标签（顶部/底部反转）
- directional: 方向性标签（三分类）
- return_sign: 收益符号标签（二分类）
- dip_recovery: Dip+Recovery 标签（反转策略核心）
- excess_return: 超额收益标签
- simple_return: 简单正负收益标签
- pump_dump: Pump+Dump 标签（dip_recovery 的镜像，看空信号）
"""

from src.labels.registry import (
    register_label_strategy,
    get_label_strategy,
    list_label_strategies,
)

from src.labels.reversal import generate_reversal_labels
from src.labels.directional import generate_directional_labels, generate_return_sign_labels
from src.labels.dip_recovery import (
    generate_dip_recovery_labels,
    generate_excess_return_labels,
    generate_simple_return_labels,
)
from src.labels.pump_dump import generate_pump_dump_labels
from src.labels.dip_recovery_v1 import generate_dip_recovery_v1_labels

__all__ = [
    "register_label_strategy",
    "get_label_strategy",
    "list_label_strategies",
    "generate_reversal_labels",
    "generate_directional_labels",
    "generate_return_sign_labels",
    "generate_dip_recovery_labels",
    "generate_excess_return_labels",
    "generate_simple_return_labels",
    "generate_pump_dump_labels",
    "generate_dip_recovery_v1_labels",
]
