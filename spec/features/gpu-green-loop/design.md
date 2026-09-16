# GPU Green Loop Design

## Table of contents

- [Measurement boundary](#measurement-boundary)
- [Runtime architecture](#runtime-architecture)
- [Metrics](#metrics)
- [Correctness gates](#correctness-gates)
- [GEPA search contract](#gepa-search-contract)
- [Optimization sequence](#optimization-sequence)

## Measurement boundary

The primary functional unit is one inference patch. The primary score is
patches per GPU joule; patches per second is secondary. Model loading and final
COG writing are reported separately from the measured inference loop so compute
changes are not hidden by fixed startup or output costs.

End-to-end runtime remains a required supporting metric because production
energy also includes raster reads, preprocessing, host-to-device copies, and
prediction assembly.

## Runtime architecture

The benchmark runs inside the HASTE CUDA 12.4 training image with one physical
GPU exposed by Docker and addressed as logical device 0. One persistent
`nvidia-smi` process samples NVML power, utilization, and memory every 50 ms
inside the same container. The evaluator clamps samples to the synchronized
inference interval before integrating energy.

The fixture contains a deterministic GeoTIFF and checkpoint generated without
external data or credentials. Fixture generation uses rasterio and preserves a
known CRS and affine transform.

## Metrics

Each measured iteration records:

- Synchronized inference-loop wall time.
- Model setup, batch preparation, warm-up, COG write, and total benchmark time.
- Process CPU time.
- GPU energy in joules, integrated from NVML power samples.
- Mean and peak GPU utilization.
- Peak allocated and reserved CUDA memory.
- Patch throughput and patches per joule.

Results retain raw samples. Summaries use medians and report every configured
iteration rather than selecting the best run.

## Correctness gates

The candidate must preserve:

- Output width, height, CRS, transform, nodata, compression, and tiling.
- Exact class-map agreement where possible.
- At least 99.9% class-map agreement when mixed-precision ties change an
  otherwise equivalent argmax.
- Finite logits and valid class values.

A failed correctness gate invalidates performance and energy improvements.

## GEPA search contract

GEPA evolves one inference kernel with this interface:

```python
def predict_batch(task, images, device):
    """Return finite logits with shape (batch, classes, height, width)."""
```

The benchmark, not the candidate, owns fixtures, warm-up, CUDA synchronization,
NVML sampling, class reduction, COG writing, and correctness checks. The
adapter rejects candidates that import unsafe modules, call dynamic execution
or file APIs, exceed the source-size limit, fail syntax validation, return an
invalid tensor, or miss the 99.9% FP32 agreement threshold.

Each search runs in a non-root Docker container with networking disabled, all
Linux capabilities dropped, a read-only root filesystem, one selected GPU,
read-only fixtures and candidates, and candidate-specific output directories.
Each candidate process has a 900-second hard timeout because imports from the
host's Docker `vfs` storage can take several minutes before measured inference
starts. The current host's threaded cgroup v2 configuration cannot enforce
Docker memory or PID limits; AST policy and serialized execution reduce that
residual risk. The first pilot uses four balanced repetitions per candidate and a
12-proposal GEPA budget.

The evaluator interleaves the fixed BF16 seed with every candidate and
alternates execution order to reduce shared-GPU and warm-state bias. GEPA's
Pareto objectives are seed-normalized patches per second and reserved CUDA
memory efficiency. Their equal geometric mean supplies GEPA's required scalar
guide score, but the final report preserves all non-dominated candidates and
selects no winner automatically. A maximum 10% deviation from the median
paired throughput ratio rejects measurements destabilized by contention.

FP32 remains the prediction oracle. Raw paired measurements, FP32-relative
diagnostics, rejection feedback, and board-level energy remain available for
reflection and audit. Energy does not affect search ranking on a shared GPU;
an energy-based comparison requires a later run with exclusive GPU access.

Repository-wide GPU discovery remains separate from mutation. A later discovery
pass may inspect all HASTE code and propose additional bounded candidate
contracts, but executable search never receives unrestricted host or repository
write access.

## Optimization sequence

1. Establish the FP32 single-A100 baseline.
2. Add A100 BF16 autocast and compare it independently.
3. Run a throughput/memory Pareto GEPA pilot over the inference kernel.
4. Add pinned host memory and nonblocking transfers.
5. Tune batch size and DataLoader settings.
6. Apply the harness to embedding and bounded training.
7. Expand GEPA only through new measured candidate contracts.
8. Re-evaluate frontier candidates on an exclusive GPU for energy ranking.
