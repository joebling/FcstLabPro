#!/bin/bash
# v0302 Alpha Validation Experiments Runner
# ==========================================

cd /Users/qiubling/Desktop/projects/FcstLabPro
source venv_py310/bin/activate

echo "========================================"
echo "Running v0302 Alpha Validation Experiments"
echo "========================================"
echo ""

EXPERIMENTS=(
    # "e01_random_label.py"
    "e02_continuous_ic.py"
    "e03_no_ma.py"
    "e04_init_train_sensitivity.py"
    "e05_newey_west.py"
    "e06_bootstrap_ci.py"
    "e07_multi_asset.py"
    "e08_threshold_sensitivity.py"
    "e09_horizon_sensitivity.py"
    # "e10_bear_regime.py"
)

SCRIPT_DIR="experiments/weekly/v0302_alpha_validation"

for exp in "${EXPERIMENTS[@]}"; do
    echo "Running $exp ..."
    python "$SCRIPT_DIR/$exp"
    echo "Done: $exp"
    echo "---"
done

echo ""
echo "========================================"
echo "All experiments completed!"
echo "========================================"
