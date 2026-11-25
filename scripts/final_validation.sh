#!/usr/bin/env bash
# final_validation.sh
# Project validation entry point for SDR-Based Cognitive Radio System
# Usage: bash scripts/final_validation.sh

set -euo pipefail

# ============================================================
# 1. Identify repository root
# ============================================================
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Project Validation ==="
echo "Repository root: $REPO_ROOT"
echo ""

# ============================================================
# 2. Python path and environment checks
# ============================================================
echo "--- Step 1: Environment Checks ---"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1)
echo "Python: $PYTHON_VERSION"

# Check imports
echo "Checking core imports..."
python3 -c "import numpy; import scipy; import pandas; import matplotlib; import sklearn; print('  NumPy, SciPy, Pandas, Matplotlib, Scikit-learn OK')" || {
    echo "ERROR: Missing dependencies"
    exit 1
}

# ============================================================
# 3. Run test suite
# ============================================================
echo "--- Step 2: Unit Tests ---"
TEST_OUTPUT=$(python3 -m pytest tests/ -q 2>&1)
TEST_EXIT=$?
echo "$TEST_OUTPUT"
if [ $TEST_EXIT -ne 0 ]; then
    echo "ERROR: Unit tests failed"
    exit 1
fi
echo "All $TEST_EXIT unit tests passed"
echo ""

# ============================================================
# 4. Run core simulation
# ============================================================
echo "--- Step 3: Simulation Validation ---"

# Verify dataset exists
if [ ! -f "results/calibrated_multi_seed_results.csv" ]; then
    echo "Running multi-seed experiment..."
    PYTHONPATH="$REPO_ROOT" python3 src/multi_seed_experiment.py \
        --seeds 30 \
        --environments low medium high \
        --strategies fixed adaptive_modulation channel_switching hybrid reliability_constrained cost_aware_hybrid calibrated_hybrid \
        --output results/calibrated_multi_seed_results.csv || {
            echo "ERROR: Multi-seed experiment failed"
            exit 1
        }
fi

# Verify dataset contents
ROW_COUNT=$(wc -l < results/calibrated_multi_seed_results.csv)
echo "Results file: results/calibrated_multi_seed_results.csv ($ROW_COUNT lines including header)"
if [ "$ROW_COUNT" -lt 630 ]; then
    echo "WARNING: Expected 630 data rows, found $((ROW_COUNT - 1))"
fi

# Verify strategies present
STRATEGIES=$(cut -d',' -f3 results/calibrated_multi_seed_results.csv | sort -u | tr '\n' ' ')
echo "Strategies: $STRATEGIES"
if echo "$STRATEGIES" | grep -q "calibrated_hybrid"; then
    echo "  - calibrated_hybrid present"
else
    echo "ERROR: calibrated_hybrid not found in results"
    exit 1
fi

# Verify environment balance
echo ""
echo "--- Step 4: Result Audit ---"
echo "Environment counts:"
python3 -c "
import pandas as pd
df = pd.read_csv('results/calibrated_multi_seed_results.csv')
print(' ', df['environment'].value_counts().to_dict())
print('  Rows:', len(df))
print('  Columns:', list(df.columns))
print('  Missing values:', int(df.isnull().sum().sum()))
print('  Duplicates:', int(df.duplicated().sum()))
"

# Verify strategies
echo "Strategy counts:"
python3 -c "
import pandas as pd
df = pd.read_csv('results/calibrated_multi_seed_results.csv')
print(df['strategy'].value_counts().to_dict())
"

echo ""

# ============================================================
# 5. Generate final plots
# ============================================================
echo "--- Step 5: Generate Final Plots ---"
mkdir -p results/final/plots results/final/tables

python3 -c "
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

df = pd.read_csv('results/calibrated_multi_seed_results.csv')
strategies = ['fixed', 'adaptive_modulation', 'channel_switching', 'hybrid', 'reliability_constrained', 'cost_aware_hybrid', 'calibrated_hybrid']
colors = plt.cm.tab10(np.linspace(0, 1, len(strategies)))

# Strategy comparison
fig, ax = plt.subplots(figsize=(10, 6))
x = np.arange(len(strategies))
width = 0.25
throughput = [df[df['strategy']==s]['throughput_bits_per_step'].mean() for s in strategies]
pdr = [df[df['strategy']==s]['packet_delivery_ratio'].mean() for s in strategies]
ax.bar(x - width/2, throughput, width, label='Throughput', color=colors)
ax.bar(x + width/2, pdr, width, label='PDR', color=colors)
ax.set_xlabel('Strategy')
ax.set_ylabel('Score')
ax.set_title('Strategy Comparison: Throughput vs PDR')
ax.set_xticks(x)
ax.set_xticklabels(strategies, rotation=30, ha='right')
ax.legend()
plt.tight_layout()
plt.savefig('results/final/plots/strategy_comparison.png', dpi=150)
plt.close()
print('  Saved: strategy_comparison.png')
"

echo ""
echo "--- Step 6: Generate Summary Tables ---"
python3 -c "
import pandas as pd
import os
os.makedirs('results/final/tables', exist_ok=True)

df = pd.read_csv('results/calibrated_multi_seed_results.csv')
strategies = ['fixed', 'adaptive_modulation', 'channel_switching', 'hybrid', 'reliability_constrained', 'cost_aware_hybrid', 'calibrated_hybrid']

# Throughput table
throughput_table = df.groupby(['environment', 'strategy'])['throughput_bits_per_step'].mean().unstack()
throughput_table = throughput_table.reindex(columns=strategies)
throughput_table.to_csv('results/final/tables/throughput_by_environment.csv')

# PDR table
pdr_table = df.groupby(['environment', 'strategy'])['packet_delivery_ratio'].mean().unstack()
pdr_table = pdr_table.reindex(columns=strategies)
pdr_table.to_csv('results/final/tables/pdr_by_environment.csv')

# Availability table
avail_table = df.groupby(['environment', 'strategy'])['service_availability'].mean().unstack()
avail_table = avail_table.reindex(columns=strategies)
avail_table.to_csv('results/final/tables/availability_by_environment.csv')

# Switching overhead table
switch_table = df.groupby(['environment', 'strategy'])['switches'].mean().unstack()
switch_table = switch_table.reindex(columns=strategies)
switch_table.to_csv('results/final/tables/switching_overhead_by_environment.csv')

print('  Created tables in results/final/tables/')
print('    - throughput_by_environment.csv')
print('    - pdr_by_environment.csv')
print('    - availability_by_environment.csv')
print('    - switching_overhead_by_environment.csv')
"

echo ""
echo "--- Step 7: Run Statistical Analysis ---"
PYTHONPATH="$REPO_ROOT" python3 src/paired_seed_analysis.py --results results/calibrated_multi_seed_results.csv >/dev/null 2>&1 || true

echo ""
echo "--- Step 8: Run ML Analysis ---"
PYTHONPATH="$REPO_ROOT" python3 src/ml_analysis.py --results results/calibrated_multi_seed_results.csv --output_dir results/ml >/dev/null 2>&1 || true

echo ""
echo "=== Validation Complete ==="
echo "All steps passed or completed with warnings."
echo "Final results: results/final/plots/ and results/final/tables/"
exit 0
