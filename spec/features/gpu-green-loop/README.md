# GPU Green Loop

## Table of contents

- [Status](#status)
- [Goal](#goal)
- [Scope](#scope)
- [Phase 1 baseline](#phase-1-baseline)
- [Phase 2 BF16 result](#phase-2-bf16-result)
- [GEPA inference adapter](#gepa-inference-adapter)
- [Reproduce and start](#reproduce-and-start)
- [Agent handoff](#agent-handoff)
- [Success criteria](#success-criteria)

## Status

**Phases 1 and 2 complete; GEPA adapter implemented.** FP32 and BF16 have
canonical results. Autonomous inference search is ready but has not started:
the shared GPU produced unstable paired throughput during calibration, and a
reflection model and its credentials still need to be configured.

## Goal

Measure and reduce GPU energy per inference work unit without changing HASTE's
predictions or geospatial output contract. The loop must report direct GPU
energy from NVML alongside runtime, throughput, utilization, and peak memory.

## Scope

Phase 1 covers `docker/training/code/inference.py` on one NVIDIA A100. Later
phases will cover MOSAIKS/DINOv2 embedding, bounded training, multi-GPU scaling,
and additional GEPA searches over constrained subsystem contracts.

The generic EMU CPU profiler is out of scope because it does not expose CUDA
devices or contain HASTE's GDAL/Conda runtime.

## Phase 1 baseline

Five FP32 runs used the same fixed U-Net/ResNeXt-50 state, 2,048 × 2,048
GeoTIFF, 320 patches, batch size 8, and NVIDIA A100 80 GB PCIe.

| Metric | Median |
|---|---:|
| Inference time | 0.866 s |
| GPU energy | 257.7 J |
| Throughput | 369.4 patches/s |
| Energy efficiency | 1.242 patches/J |
| Mean GPU power | 294.3 W |
| Peak allocated CUDA memory | 459,944,448 bytes |
| COG write time | 0.152 s |

All five class-map arrays have SHA-256
`503806d5a602c7c3f17648f7c268f37b06cb9acb1a5f6a19d886483ff02d3b9b`.
Each output is a tiled LZW COG with EPSG:32604, the expected transform and
bounds, nodata 255, and class values 0–3. Raw local results are under
`.gpu-green-loop/results/` and remain excluded from Git.

## Phase 2 BF16 result

Five BF16 runs used the Phase 1 checkpoint, raster, batches, and A100. Every
run produced the same candidate class map and passed the 99.9% agreement gate.

| Metric | FP32 median | BF16 median | Change |
|---|---:|---:|---:|
| Inference time | 0.866 s | 0.792 s | **-8.55%** |
| GPU energy | 257.7 J | 232.2 J | **-9.88%** |
| Throughput | 369.4 patches/s | 403.9 patches/s | **+9.35%** |
| Energy efficiency | 1.242 patches/J | 1.378 patches/J | **+10.96%** |
| Peak CUDA allocation | 459,944,448 bytes | 430,393,856 bytes | **-6.42%** |
| Peak CUDA reservation | 654,311,424 bytes | 511,705,088 bytes | **-21.79%** |

BF16 agreed with FP32 on 99.9065% of 20,971,520 pixels. Production inference
now defaults to BF16 on Ampere-or-newer GPUs and remains FP32 on CPUs and older
GPUs. Set `inference.precision` to `fp32` to force the original behavior or to
`bf16` to require BF16 support explicitly.

## GEPA inference adapter

The GEPA 0.1.4 adapter evolves only
`predict_batch(task, images, device)`. Candidate code cannot control fixtures,
timing, telemetry, correctness, or output writing. Source policy and a
hardened persistent Docker container block unsafe imports, networking, file
access, subprocesses, capabilities, and root execution.

Search now treats throughput and CUDA reserved-memory efficiency as separate
Pareto objectives. An equal geometric mean guides GEPA's required scalar
search, but the report declares no automatic winner and writes every
non-dominated candidate under `.gpu-green-loop/gepa/search/frontier/`. GPU
energy remains in diagnostics and does not affect ranking while the GPU is
shared. A future energy-ranking pass requires exclusive access because NVML
power is board-level rather than process-level.

Each candidate and the fixed BF16 control run in one process with the model and
batches loaded once. Four repetitions alternate control/candidate order. A
candidate is rejected when a paired throughput ratio differs by more than 10%
from the median, preventing transient contention from becoming an apparent
optimization.

The latest byte-identical seed calibration on GPU 3 passed 99.9065% FP32
agreement and produced normalized throughput `1.00005` and memory efficiency
`1.00000`. It was correctly rejected as too noisy: the four throughput ratios
ranged from approximately `0.60` to `1.12` as another user's workload became
active. No autonomous proposals have been evaluated.

## Reproduce and start

Run commands from the repository root. This host does not run systemd, so keep
the daemon in a separate terminal if it is not already running:

```bash
sudo dockerd --host=unix:///var/run/docker.sock
```

Verify CUDA access and build the pinned HASTE image:

```bash
sudo docker run --rm --gpus all \
  nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
sudo docker build -f docker/training/Dockerfile \
  -t haste-training:gpu-green-loop .
```

Generate the five-run FP32 oracle if `.gpu-green-loop/results/fp32-summary.json`
is absent:

```bash
HASTE_DOCKER_COMMAND='sudo docker' \
HASTE_GPU_INDEX=0 HASTE_GPU_PRECISION=fp32 \
  tools/gpu-green-loop/run_phase1.sh
```

Install the isolated GEPA environment and calibrate on the selected GPU:

```bash
python -m venv .gpu-green-loop/gepa-venv
.gpu-green-loop/gepa-venv/bin/pip install \
  -r tools/gpu-green-loop/gepa/requirements.txt

HASTE_DOCKER_COMMAND='sudo docker' \
  .gpu-green-loop/gepa-venv/bin/python \
  tools/gpu-green-loop/gepa/gepa_gpu_adapter.py \
  seed --gpu 0 --repetitions 4 --timeout-seconds 900
```

Do not start search unless calibration is accepted. Configure a LiteLLM model
and its provider credential outside the repository, then begin with a small
proposal budget:

```bash
export GEPA_REFLECTION_MODEL='provider/model-name'
export PROVIDER_API_KEY='...'

HASTE_DOCKER_COMMAND='sudo docker' \
  .gpu-green-loop/gepa-venv/bin/python \
  tools/gpu-green-loop/gepa/gepa_gpu_adapter.py \
  search --gpu 0 --repetitions 4 --candidate-budget 3 \
  --timeout-seconds 900
```

Search outputs are written beneath `.gpu-green-loop/gepa/search/`; `report.json`
contains the full Pareto frontier and all accepted or rejected evaluations.

## Agent handoff

See [agent-handoff.md](agent-handoff.md) for migration state, design decisions,
known host limitations, a new-machine checklist, and the exact files a future
agent should inspect first. Generated fixtures and raw run artifacts are not
committed and must be regenerated on the destination machine.

## Success criteria

- A fixed workload runs repeatedly on one selected GPU.
- Warm-up work is excluded from measurements.
- Timings synchronize CUDA before starting and stopping.
- NVML samples power, utilization, and memory without requiring application
  credentials.
- Output class values and raster CRS, transform, dimensions, nodata, and
  tiling remain valid.
- Baseline and candidate run in the same image with the same fixture.
- Results include work units per second and work units per joule.
