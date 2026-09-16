#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
IMAGE="${HASTE_GPU_IMAGE:-haste-training:gpu-green-loop}"
GPU="${HASTE_GPU_INDEX:-0}"
RUNS="${HASTE_GPU_RUNS:-5}"
PRECISION="${HASTE_GPU_PRECISION:-fp32}"
RESULTS="${HASTE_GPU_RESULTS:-$REPO_ROOT/.gpu-green-loop/results}"
FIXTURES="${HASTE_GPU_FIXTURES:-$REPO_ROOT/.gpu-green-loop/fixtures}"
read -r -a DOCKER_COMMAND <<< "${HASTE_DOCKER_COMMAND:-docker}"

if [[ "$PRECISION" != "fp32" && "$PRECISION" != "bf16" ]]; then
  echo "error: HASTE_GPU_PRECISION must be fp32 or bf16" >&2
  exit 1
fi

mkdir -p "$RESULTS" "$FIXTURES"

if ! "${DOCKER_COMMAND[@]}" info >/dev/null 2>&1; then
  echo "error: Docker is unavailable; set HASTE_DOCKER_COMMAND if needed" >&2
  exit 1
fi

for run in $(seq 1 "$RUNS"); do
  output="$RESULTS/$PRECISION-run-$run"
  mkdir -p "$output"
  "${DOCKER_COMMAND[@]}" run --rm \
    --gpus "device=$GPU" \
    --network none \
    --user "$(id -u):$(id -g)" \
    --env HOME=/tmp \
    --volume "$SCRIPT_DIR:/benchmark:ro" \
    --volume "$FIXTURES:/fixtures" \
    --volume "$output:/results" \
    "$IMAGE" \
    python /benchmark/gpu_inference_benchmark.py \
      --precision "$PRECISION" \
      --gpu 0 \
      --fixture-dir /fixtures \
      --output /results

  if [[ "$PRECISION" != "fp32" ]]; then
    baseline="$RESULTS/fp32-run-$run/predictions-fp32.npy"
    if [[ ! -f "$baseline" ]]; then
      echo "error: missing FP32 baseline for run $run: $baseline" >&2
      exit 1
    fi
    python "$SCRIPT_DIR/compare_predictions.py" \
      "$baseline" \
      "$output/predictions-$PRECISION.npy" \
      --minimum-agreement 0.999 \
      > "$output/comparison-to-fp32.json"
  fi
done

python "$SCRIPT_DIR/summarize_runs.py" \
  "$RESULTS"/"$PRECISION"-run-*/"metrics-$PRECISION.json" \
  --output "$RESULTS/$PRECISION-summary.json"
