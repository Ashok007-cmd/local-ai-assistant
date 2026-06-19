#!/usr/bin/env bash
# Run benchmarks for each model individually, saving results incrementally.
# Handles the 10-minute timeout by saving after each model.
set -euo pipefail

cd "$(dirname "$0")/.."
OUTPUT_DIR="benchmarks"
mkdir -p "$OUTPUT_DIR"
rm -f "$OUTPUT_DIR"/results_*.csv "$OUTPUT_DIR"/benchmark_results_all.csv

ALL_RESULTS_CSV="$OUTPUT_DIR/benchmark_results_all.csv"
HEADER_WRITTEN=false

MODELS=(
    "llama3.2:3b"
    "gemma3:4b"
    "mistral:7b"
)

for MODEL in "${MODELS[@]}"; do
    echo ""
    echo "========================================================================"
    echo "Benchmarking model: $MODEL"
    echo "========================================================================"
    echo ""

    # Run a single-model benchmark using the Python API directly
    python3 -c "
import sys, csv, json, time, math
sys.path.insert(0, '.')
from benchmarks.benchmark_runner import (
    run_single_benchmark, BENCHMARK_PROMPTS, get_available_models,
)
import logging
logging.basicConfig(level=logging.INFO)

model = '$MODEL'
print(f'Running warmup for {model}...')
run_single_benchmark(model=model, prompt='Say hello.', warmup=True)

all_results = []
for pdef in BENCHMARK_PROMPTS:
    for run_idx in range(1, 4):
        print(f'  Run {run_idx}/3: {pdef[\"name\"]}')
        result = run_single_benchmark(
            model=model,
            prompt=pdef['prompt'],
            system_prompt=pdef.get('system'),
        )
        # Override prompt_name to include the group name
        result.prompt_name = f'{pdef[\"name\"]}_run{run_idx}'
        all_results.append(result)

# Save to CSV
csv_path = '$OUTPUT_DIR/results_${MODEL//:/_}.csv'
with open(csv_path, 'w', newline='') as f:
    if all_results:
        from dataclasses import asdict
        writer = csv.DictWriter(f, fieldnames=asdict(all_results[0]).keys())
        writer.writeheader()
        for r in all_results:
            writer.writerow(asdict(r))

ok = sum(1 for r in all_results if r.success)
total = len(all_results)
print(f'Model {model}: {ok}/{total} runs successful, avg {sum(r.tokens_per_second for r in all_results if r.success)/max(ok,1):.1f} tok/s')
print(f'Saved to {csv_path}')
" 2>&1 | tee "$OUTPUT_DIR/benchmark_${MODEL//:/_}.log"

done

echo ""
echo "All models benchmarked. Combining results..."
python3 -c "
import csv, glob, os

all_fields = set()
rows = []
for fname in sorted(glob.glob('$OUTPUT_DIR/results_*.csv')):
    with open(fname) as f:
        reader = csv.DictReader(f)
        for row in reader:
            all_fields.update(row.keys())
            rows.append(row)

fields = sorted(all_fields)
outpath = '$ALL_RESULTS_CSV'
with open(outpath, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

print(f'Combined {len(rows)} results into {outpath}')
print(f'Models: {sorted(set(r[\"model\"] for r in rows))}')
"
