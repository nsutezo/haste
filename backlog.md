# Energy Efficiency Backlog (nsutezo/haste)

Last updated: 2026-09-17 22:41 UTC (fourth run — first Python-side win).

## Completed this run
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

## New backlog items found this run (unimplemented)

### MEDIUM
- Shared sort between `_average_precision` and `_precision_recall_curve`
  in `hastelib/src/hastegeo/core/utils/assessment.py`. Both do
  `sorted(zip(y_score, y_true), ..., reverse=True)` on the same pair
  sequence back-to-back. Hoist once → saves one O(n log n) per report.
  Non-trivial: changes helper API. Hold until profiled as real hot path.
- `harden_gdal` driver-list double call in
  `hastelib/src/hastegeo/core/utils/gdal_security.py`: the list-comp
  calls `gdal.GetDriver(i)` twice per index. Trivial local-var fix.
  Import-time only, small win.

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
Next run should: (1) verify PRs #1, #5 and the HelpDocs branch for CI
status / maintainer comments (Task 4); (2) do the shared-sort refactor
in `assessment.py` if hot-path profiling supports it; (3) apply the
trivial `harden_gdal` fix (bundle with other small wins); (4) broader
dead-asset sweep across `ui/src/assets/**`; (5) Task 6 (measurement
infrastructure) still not addressed — a benchmark suite for
`hastegeo.core.utils.assessment` would let us regression-guard PR #5.
