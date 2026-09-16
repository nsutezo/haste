# GPU Green Loop Plan

## Table of contents

- [Phases](#phases)
- [Current constraints](#current-constraints)
- [Expected ranges](#expected-ranges)

## Phases

| Phase | Work | Agent | Status |
|---|---|---|---|
| 1 | Build deterministic single-A100 inference evaluator | `backend-dev` | Complete |
| 1 | Validate output and measurements | `backend-validation` | Complete |
| 2 | Add and validate the BF16 candidate | `backend-dev` | Complete |
| 2 | Add transfer and loader candidates separately | `backend-dev` | Pending |
| 2 | Validate transfer and loader accuracy and energy | `backend-validation` | Pending |
| 3 | Extend evaluator to MOSAIKS and DINOv2 | `gis` | Pending |
| 3 | Validate CRS, footprint alignment, and embeddings | `backend-validation` | Pending |
| 4 | Add bounded single- and multi-GPU training workloads | `backend-dev` | Pending |
| 4 | Compare time-to-result and joules-to-result | `backend-validation` | Pending |
| 5 | Add isolated GEPA inference search adapter | `backend-dev` | Complete |
| 5 | Validate seed evaluation and sandbox gates | `backend-validation` | Blocked by unstable shared-GPU throughput |
| 6 | Add repository-wide GPU discovery and bounded contracts | `backend-dev` | Pending |
| All | Record run metadata and outcomes | `orchestrator` | In progress |

## Current constraints

- The host has four NVIDIA A100 80 GB PCIe GPUs.
- Docker Engine 25.0.3 and NVIDIA Container Toolkit 1.17.8 are installed.
- The Docker daemon runs without systemd in the current host session.
- The host Python environment does not include PyTorch.
- HASTE does not commit a model checkpoint or inference raster fixture.
- All four GPUs currently host unrelated compute processes.
- Throughput search may run under contention only when balanced paired ratios
  pass the 10% stability gate.
- Board-level energy ranking is deferred until one GPU is exclusively available.

## Expected ranges

These are hypotheses, not acceptance criteria:

| Candidate | Expected end-to-end improvement |
|---|---:|
| BF16 inference | 15-40% |
| Pinned/nonblocking transfer | 5-15% when transfer-bound |
| Batch and worker tuning | 10-30% |
| Embedding cache/pipeline changes | 5-30% |
| A100 training tuning | 5-20% |
