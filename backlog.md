# Energy Efficiency Backlog (nsutezo/haste)

Last updated: 2026-09-18 14:47 UTC (fifth run).

## Completed this run (2026-09-18)
- [DONE, PR CREATED] **Code-Level, MEDIUM** — Shared sort in
  `hastelib/src/hastegeo/core/utils/assessment.py`: `_average_precision`
  and `_precision_recall_curve` each independently sorted the same
  `zip(y_score, y_true)` sequence descending by score. Both now accept
  an optional `sorted_pairs` kwarg; `compute_assessment_report` sorts
  once (when `x > 0`) and shares it. Removes one O(n log n) sort per
  report. 16/16 test_assessment.py tests pass.
  Benchmark (standalone script, 60k-label synthetic workload, 15 iter +
  3 warmup, wall-clock via `time.perf_counter`, 3-4 trials each side vs
  `main`): baseline median 99-112ms, candidate median ~87ms consistently
  — 12-22% wall-time reduction. No profiler/verifier tooling present in
  this sandbox instance (referenced in earlier memory but not found on
  disk this run) — used a standalone repro script instead, included in
  PR body reproduction steps.
- [DONE, bundled in same PR] **Code-Level, MEDIUM** — `harden_gdal`
  driver-list double-call fix in `gdal_security.py` (from prior run's
  backlog). Rewrote as generator+filter to fetch each driver once.
  Trivial, import-time only, bundled with the above into one PR.
- Branch: `efficiency/shared-sort-assessment-and-gdal-driver-fix`. PR
  title: "[efficiency-improver] perf(assessment,gdal): hoist shared
  sort in PR-curve helpers; dedupe GDAL driver lookup".

## State verification done this run
- Confirmed PR #1 (route code-splitting) and PR #5 (confusion-matrix
  fusion) both still OPEN, draft, unmerged, no new comments beyond
  their own creation. No action needed this run (Task 4).
- Issues #3 and #4 are stale "workflow failed" auto-issues from
  earlier oversized-patch failures (35113540753, 35239489111) — both
  predate later successful runs. Recommended maintainer action: close
  both as resolved/superseded (added to Suggested Actions).
- Could not verify existence of the previously-claimed
  `efficiency/optimize-helpdocs-images` branch (no git network access
  in this sandbox to check `ls-remote`; PR search hit GitHub API rate
  limit). Deferred verification to next run — do NOT assume it exists
  or doesn't; check again first thing.

## Completed previous run (2026-09-17)
- [DONE, PR #5 OPEN] **Code-Level, HIGH** — Single-pass confusion matrix
  in `hastelib/src/hastegeo/core/utils/assessment.py::compute_assessment_report`.
  Fused 5 O(n) generator sums + a `y_pred` list comprehension into one
  O(n) loop; derived `fn`/`tn` from `x = tp + fn`, `n - x = fp + tn`.
  Return shape unchanged; 16/16 tests in `test_assessment.py` pass.
  Verifier: SIGNIFICANT_IMPROVEMENT on `wall_time_s` (n=20 per side),
  77.4ms → 69.1ms, `delta_pct = -10.74%`, `p = 0.0`, Cliff's δ = 0.94.
  Profiler (median of 5, full workload): CPU -4.85%, wall -5.27%,
  energy -9.36%. Final verifier gate = TESTS_FAILED, but only because
  the wider suite can't collect two modules needing `libgdal.so.35` and
  one needing `pystac` — both unrelated to this change.

## Open opportunities from earlier runs (still unimplemented)

### MEDIUM
- Azure Cosmos DB `SELECT *` in
  `hastelib/src/hastegeo/core/data_layer/azure_cosmos_db_data_layer.py`
  (`load_all`, `load_all_from_partition`, `delete_all_from_partition`,
  `load_bounded`). Needs field-usage check before narrowing.
- Vendored third-party JS files under `ui/src/assets/js/`
  (`azure-maps-image-exporter.js`, `azure-maps-swipe-map.min.js`) — not
  confirmed unused yet.

### LOW
- `@fluentui/react-icons` import style not verified for tree-shaking.
- Broader dead-asset sweep across `ui/src/assets/**` (beyond helpDocs) —
  still not done across 4 runs.
- Nested loops in `embed_buildings.py`, `stats.py`, `tbparser.py` etc.
  — likely small bounded collections; needs profiling first.

## Completed previously (open PRs, unmerged)
- PR #1 — Route-level code splitting in `ui/src/Components/AppBody.jsx`
  (main JS chunk 1.49MB → 119KB, -92%).
- `efficiency/optimize-helpdocs-images` — HelpDocs WebP + dead-asset
  removal (`ui/src/assets/helpDocs` 17MB → 1.1MB, -94%).

## Cross-run reminder
Do NOT trust "DONE" claims in memory without cross-checking actual
repo/PR state at the start of every run.

## Backlog cursor
Next run should: (1) verify PRs #1, #5, and the new shared-sort PR for
CI status / maintainer comments (Task 4); (2) confirm/deny existence of
the `efficiency/optimize-helpdocs-images` branch claimed in earlier
memory (rate-limited last run before it could be checked); (3) Cosmos
DB `SELECT *` field-usage investigation; (4) broader dead-asset sweep
across `ui/src/assets/**`; (5) Task 6 (measurement infrastructure)
still not addressed — consider committing the standalone
`bench_assessment.py`-style script (currently only in PR description)
as a proper `hastelib/tests/perf/` or `.github/tools/` benchmark so
future runs don't have to reconstruct it from scratch each time
(propose via issue first, since it's new tooling).
