# ADR 0001: Use GEPA for GPU Code Search

## Table of contents

- [Status](#status)
- [Context](#context)
- [Decision](#decision)
- [Consequences](#consequences)

## Status

Accepted for an isolated inference pilot.

## Context

The GPU Green Loop has deterministic A100 measurements, direct energy
telemetry, prediction agreement checks, and geospatial output gates. The next
step needs reflective autonomous search that can consume rich failure and
profiling feedback while retaining multiple performance objectives.

OpenEvolve was the initial candidate. GEPA now provides a maintained
`optimize_anything` interface for code candidates, reflective feedback, and
Pareto-aware objective scores.

## Decision

Use GEPA 0.1.4 for autonomous GPU code search. Start with an inference-only
candidate contract and a 12-proposal budget.

Run candidates in a dedicated Docker container with no network, no Linux
capabilities, a read-only root filesystem, serialized execution, hard process
timeouts, and one A100. The current host cannot apply Docker memory or PID
limits because its cgroup v2 hierarchy is in threaded mode. Keep benchmark
controls outside candidate code and reject any candidate that fails source
policy, execution, prediction agreement, or COG validation.

Allow repository-wide read-only discovery later, but require a measured,
reviewed candidate contract before GEPA can mutate another subsystem.

## Consequences

- GEPA receives actionable traces instead of one opaque efficiency score.
- The initial search cannot alter loaders, embedding, training, or unrelated
  HASTE code.
- Expanding coverage requires a new evaluator contract for each functional
  unit.
- Autonomous search requires a separately configured reflection-model
  credential; the repository stores only the model identifier and never the
  credential.
