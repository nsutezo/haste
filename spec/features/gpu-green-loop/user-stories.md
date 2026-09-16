# GPU Green Loop User Stories

## Table of contents

- [Stories](#stories)
- [Agent assignment map](#agent-assignment-map)

## Stories

### GL-1: Reproducible inference measurement

As a HASTE maintainer, I want a deterministic single-GPU inference workload so
that candidate changes can be compared on identical inputs.

**Acceptance criteria**

- The fixture requires no external service or credential.
- The selected GPU, seed, workload size, and software versions are recorded.
- Repeated runs emit machine-readable raw measurements.

### GL-2: Energy-aware optimization

As a HASTE maintainer, I want GPU energy and throughput measured together so
that faster changes are not accepted when they consume more energy per patch.

**Acceptance criteria**

- NVML energy is integrated over the measured interval.
- Results report patches per second and patches per joule.
- Candidate correctness is checked before performance is accepted.

### GL-3: Safe mixed precision

As a HASTE maintainer, I want BF16 inference evaluated against FP32 so that
tensor-core gains do not silently alter disaster-assessment output.

**Acceptance criteria**

- Both modes use the same checkpoint, raster, and batches.
- Class-map agreement and raster metadata checks pass.
- Any numerical tolerance is explicit in the result.

### GL-4: Isolated autonomous inference search

As a HASTE maintainer, I want GEPA to evolve measured inference kernels so that
it can discover GPU improvements without receiving unrestricted repository or
host access.

**Acceptance criteria**

- GEPA candidates can affect the measured model-forward path.
- Each candidate runs in a bounded, network-disabled container.
- Correctness failures receive a rejecting score regardless of performance.
- Raw metrics, normalized objectives, feedback, and the best candidate persist.
- The run supports a fixed candidate budget and can resume from its output.

### GL-5: Repository-wide GPU discovery

As a HASTE maintainer, I want GEPA-assisted discovery across the whole HASTE
codebase so that optimization is not permanently limited to inference.

**Acceptance criteria**

- Discovery may read all tracked source but cannot mutate it directly.
- Each proposed area identifies a functional unit and correctness gate.
- A maintainer approves a bounded candidate contract before executable search.

## Agent assignment map

| Story | Implementing agent | Validating agent |
|---|---|---|
| GL-1 | `backend-dev` | `backend-validation` |
| GL-2 | `backend-dev` | `backend-validation` |
| GL-3 | `backend-dev` | `backend-validation` |
| GL-4 | `backend-dev` | `backend-validation` |
| GL-5 | `backend-dev` | `backend-validation` |
