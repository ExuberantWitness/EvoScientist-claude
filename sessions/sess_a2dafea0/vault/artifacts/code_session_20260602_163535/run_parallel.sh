#!/bin/bash
# Parallel training launcher — runs 3 algorithms concurrently per batch.
# Usage: bash run_parallel.sh <batch_number>
#   batch 1: sac td3 ddpg
#   batch 2: td_variance attention_prior value_uncertainty
#   batch 3: dp_depth taylor_curvature gait_phase

set -e

BATCH=${1:?Usage: bash run_parallel.sh <1|2|3>}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON=/home/exuber/anaconda3/bin/python
OUTDIR=/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/sessions/sess_a2dafea0/hopper_experiments
LOGDIR=/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/sessions/sess_a2dafea0/parallel_logs

mkdir -p "$OUTDIR" "$LOGDIR"

case $BATCH in
    1) ALGOS="sac td3 ddpg" ;;
    2) ALGOS="td_variance attention_prior value_uncertainty" ;;
    3) ALGOS="dp_depth taylor_curvature gait_phase" ;;
    *) echo "Invalid batch: $BATCH (use 1, 2, or 3)"; exit 1 ;;
esac

echo "============================================"
echo "Batch $BATCH: $ALGOS"
echo "Output: $OUTDIR"
echo "Logs:   $LOGDIR"
echo "Start:  $(date)"
echo "============================================"

PIDS=""
for ALGO in $ALGOS; do
    LOGFILE="$LOGDIR/${ALGO}_batch${BATCH}.log"
    echo "  Launching $ALGO -> $LOGFILE"
    $PYTHON -u "$SCRIPT_DIR/train_all.py" \
        --algo "$ALGO" \
        --seeds 0 1 2 3 4 \
        --device cuda \
        --output-dir "$OUTDIR" \
        &> "$LOGFILE" &
    PIDS="$PIDS $!"
done

echo "PIDs:$PIDS"
echo "Waiting for batch $BATCH to complete..."

FAILED=0
for PID in $PIDS; do
    wait $PID || FAILED=$((FAILED + 1))
done

echo "============================================"
echo "Batch $BATCH done: $(date)"
if [ $FAILED -gt 0 ]; then
    echo "WARNING: $FAILED process(es) failed"
    exit 1
fi
echo "All processes completed successfully"
echo "============================================"
