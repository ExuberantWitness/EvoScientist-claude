#!/bin/bash
# Master launcher — runs all 3 batches sequentially.
# Each batch runs 3 algorithms in parallel.
# Usage: nohup bash run_all_batches.sh &> master.log &

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGDIR=/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/sessions/sess_a2dafea0/parallel_logs

echo "============================================"
echo "PARALLEL TRAINING — ALL 3 BATCHES"
echo "Start: $(date)"
echo "============================================"

for BATCH in 1 2 3; do
    echo ""
    echo ">>> Launching Batch $BATCH at $(date)"
    bash "$SCRIPT_DIR/run_parallel.sh" $BATCH
    echo "<<< Batch $BATCH completed at $(date)"
done

echo ""
echo "============================================"
echo "ALL BATCHES COMPLETE: $(date)"
echo "Results: /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/sessions/sess_a2dafea0/hopper_experiments"
echo "============================================"
