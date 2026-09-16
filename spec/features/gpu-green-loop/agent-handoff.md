# GPU Green Loop Agent Handoff

## Purpose

This branch moves HASTE GPU optimization from manual experiments toward a
bounded GEPA search. Executable mutation is intentionally limited to the
inference kernel. Repository-wide GPU opportunity discovery is a later,
read-only phase that must define a measured contract before any new subsystem
can be mutated.

## Current state

- Branch: `experiment/gpu-green-loop`
- Repository: `nsutezo/haste`
- CUDA image: `haste-training:gpu-green-loop`
- GEPA: `gepa[full]==0.1.4`
- Production inference defaults to BF16 on Ampere-or-newer CUDA devices and
  remains FP32 on CPU and older GPUs.
- The deterministic FP32 oracle and BF16 comparison are complete.
- The isolated GEPA inference adapter is implemented.
- Autonomous GEPA proposals have not run.

The GEPA candidate contract is:

```python
def predict_batch(task, images, device):
    """Return finite logits with shape (batch, classes, height, width)."""
```

The evaluator owns the model, fixtures, batches, CUDA synchronization,
telemetry, output creation, and correctness decisions. Candidate policy allows
only `torch` imports and rejects file access, networking, subprocesses,
dynamic execution, dunder access, invalid tensors, and oversized source.

## Search policy

GEPA receives two separate Pareto objectives:

- Candidate patches/s divided by the paired BF16 control patches/s.
- Paired-control reserved CUDA bytes divided by candidate reserved CUDA bytes.

An equal geometric mean is used only as GEPA's required scalar guide. The
search report selects no deployment winner and persists every non-dominated
candidate under `.gpu-green-loop/gepa/search/frontier/`.

NVML board energy remains diagnostic and has no effect on search while a GPU
is shared. Re-run frontier candidates with exclusive GPU access before making
energy claims.

Control and candidate execute in one process after shared setup and warm-up.
Four repetitions alternate AB/BA order. The evaluator rejects a candidate if
any paired throughput ratio differs by more than 10% from their median.

## Evidence

Canonical five-run BF16 results relative to FP32:

| Metric | Change |
|---|---:|
| Inference time | -8.55% |
| GPU energy | -9.88% |
| Throughput | +9.35% |
| Patches/J | +10.96% |
| Peak CUDA allocation | -6.42% |
| Peak CUDA reservation | -21.79% |
| FP32 class-map agreement | 99.9065% |

The latest byte-identical paired seed calibration produced normalized
throughput `1.00005` and memory efficiency `1.00000`, but its individual
throughput ratios ranged from approximately `0.60` to `1.12`. The 39.96%
maximum deviation correctly fails the 10% stability gate. Other users became
active on the selected GPU during the run.

Generated evidence is deliberately not committed. `.gpu-green-loop/` contains
local checkpoints, rasters, arrays, raw telemetry, GEPA environments, and
candidate outputs and remains ignored.

## New-machine bootstrap

Install a compatible NVIDIA driver, Docker Engine, NVIDIA Container Toolkit,
Python, and Git before running these commands.

```bash
git clone https://github.com/nsutezo/haste.git
cd haste
git checkout experiment/gpu-green-loop
```

If the machine does not run systemd, keep this command running in a separate
terminal:

```bash
sudo dockerd --host=unix:///var/run/docker.sock
```

Verify GPU passthrough and build the image from the repository root:

```bash
sudo docker run --rm --gpus all \
  nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
sudo docker build -f docker/training/Dockerfile \
  -t haste-training:gpu-green-loop .
```

Generate the FP32 oracle:

```bash
HASTE_DOCKER_COMMAND='sudo docker' \
HASTE_GPU_INDEX=0 HASTE_GPU_PRECISION=fp32 \
  tools/gpu-green-loop/run_phase1.sh
```

Install GEPA outside the project environment and run seed calibration:

```bash
python -m venv .gpu-green-loop/gepa-venv
.gpu-green-loop/gepa-venv/bin/pip install \
  -r tools/gpu-green-loop/gepa/requirements.txt

HASTE_DOCKER_COMMAND='sudo docker' \
  .gpu-green-loop/gepa-venv/bin/python \
  tools/gpu-green-loop/gepa/gepa_gpu_adapter.py \
  seed --gpu 0 --repetitions 4 --timeout-seconds 900
```

Configure a LiteLLM-compatible reflection model using provider-specific
environment variables. Never commit its credentials. Start with three
proposals:

```bash
export GEPA_REFLECTION_MODEL='provider/model-name'
export PROVIDER_API_KEY='...'

HASTE_DOCKER_COMMAND='sudo docker' \
  .gpu-green-loop/gepa-venv/bin/python \
  tools/gpu-green-loop/gepa/gepa_gpu_adapter.py \
  search --gpu 0 --repetitions 4 --candidate-budget 3 \
  --timeout-seconds 900
```

Use the provider's actual credential variable in place of
`PROVIDER_API_KEY`. Do not proceed when seed calibration is rejected.

## Continuation checklist

1. Confirm the new machine has exclusive or consistently scheduled access to
   one A100-class GPU.
2. Build the image and regenerate the FP32 oracle; local artifacts are not in
   Git.
3. Require seed calibration to pass before search.
4. Select and configure the reflection model without storing credentials.
5. Run a three-proposal pilot before the default 12-proposal budget.
6. Review every Pareto candidate; do not treat GEPA's scalar guide as a winner.
7. Re-run frontier candidates under exclusive access for energy ranking.
8. Add Docker memory and PID limits if the new host's cgroup hierarchy
   supports them; the original host used threaded cgroup v2 and could not.
9. Implement repository-wide discovery separately, then add measured mutation
   contracts for transfers, embeddings, and training one subsystem at a time.

## Key files

- `tools/gpu-green-loop/gepa/gepa_gpu_adapter.py`
- `tools/gpu-green-loop/gepa/seed_candidate.py`
- `tools/gpu-green-loop/gepa_pair_benchmark.py`
- `tools/gpu-green-loop/gpu_inference_benchmark.py`
- `tools/gpu-green-loop/test_gepa_gpu_adapter.py`
- `tools/gpu-green-loop/test_gpu_green_loop.py`
- `docker/training/code/inference.py`
- `docker/training/code/bda/config.py`
- `spec/features/gpu-green-loop/README.md`
- `spec/features/gpu-green-loop/design.md`
- `spec/features/gpu-green-loop/plan.md`
- `spec/architecture/decisions/0001-use-gepa-for-gpu-code-search.md`
