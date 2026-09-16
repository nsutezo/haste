# Energy Efficiency Backlog (nsutezo/haste)

Last updated: 2026-09-16 (second run, workflow run 35113540753)

## Completed this run (2026-09-16, run 35113540753)
- [DONE] **Frontend/UI + Data, HIGH** — HelpDocs image optimization.
  Branch `efficiency/optimize-helpdocs-images`, PR created (title
  `[efficiency-improver] perf(ui): optimize HelpDocs images and remove
  dead assets`). Two sub-changes:
  1. Re-encoded 11 referenced-but-unoptimized images (results-visualizer,
     8 labeling comparison JPEGs, 2 model-catalog JPEGs) to WebP q=82
     via Pillow. 5,224,322 -> 714,800 bytes (-86.3%).
  2. Discovered and deleted 12 files (~11.8MB) of **completely dead
     assets** never imported anywhere in ui/src: the entire
     `ui/src/assets/helpDocs/interactive/` folder (9 files, 7.3MB —
     these were only referenced by matching filename in unrelated
     docs/usage/*.md files pointing at a separate docs/_static/usage/
     copy, NOT the ui/src copies) plus 3 orphaned `results/` images
     (damage-visualizer.png, raw-predictions-layer.png,
     results-menu.png, 4.5MB).
  Net: ui/src/assets/helpDocs 17MB -> 1.1MB (-94%). Verified via
  `npm run build` (webp assets bundle correctly), eslint (0 new errors,
  confirmed identical pre-existing errors via git stash diff), and all
  4 existing node --test suites (66/66 pass).
  Tooling note: no image conversion tool was preinstalled (no cwebp,
  no system Pillow, no sudo). Created a throwaway Python venv
  (`python3 -m venv` + `pip install Pillow`) purely as a one-time local
  conversion tool — not a new project dependency, nothing committed.

## Completed previously
- [DONE] **Frontend/UI, HIGH** — Route-level code splitting in
  `ui/src/Components/AppBody.jsx`. Converted all routed component static
  imports to `React.lazy()` + `Suspense`. Main entry JS chunk went from
  1,489,465 bytes (406.67 kB gzip) to 119,046 bytes (36.40 kB gzip), a 92%
  reduction. HelpDocs' ~17MB of embedded screenshot images (previously
  reachable from the eager import graph) now only fetch when a user visits
  `/help-docs`. PR created: branch `efficiency/route-level-code-splitting`.

## Open opportunities (not yet implemented)

### HIGH (DONE — see "Completed this run" above)
- ~~HelpDocs images unoptimized JPEG/PNG~~ — DONE this run (PR
  `efficiency/optimize-helpdocs-images`). Also found and removed ~11.8MB
  of completely dead/unreferenced assets in the same directory tree
  (`interactive/` folder + 3 orphaned `results/` images) that weren't on
  the original backlog radar — worth a repo-wide dead-asset sweep next
  time (check `ui/src/assets/**` more broadly, not just helpDocs).

### MEDIUM
- **Azure Cosmos DB `SELECT *` queries** in
  `hastelib/src/hastegeo/core/data_layer/azure_cosmos_db_data_layer.py`
  (`load_all`, `load_all_from_partition`, `delete_all_from_partition`,
  `load_bounded`). All four queries fetch every column via `SELECT *`
  instead of naming needed fields, and `delete_all_from_partition` does a
  full `SELECT *` fetch of every item's full JSON body just to read back
  the id/partition key needed for `delete_item`. Cosmos RU cost scales with
  bytes read, so trimming to `SELECT c.id, c.partition_key ...` (or
  whichever fields callers actually use downstream in
  `hastegeo.core.processors.metadata.py`) would reduce RU consumption
  (proxy: RU charge is reported by the SDK per-request; can be measured
  with an Azurite/Cosmos emulator test harness in
  `hastelib/tests/core/data_layer/`). Needs investigation into which
  fields `MetadataProcessor.load_all()` callers actually consume before
  narrowing the projection — some callers may need the full document.
  Estimated impact: MEDIUM because Cosmos DB is one of several supported
  data-layer backends (blob/postgres/local/data-lake also exist) and usage
  volume in production is unknown.
- **Vendored third-party JS files under `ui/src/assets/js/` fail lint with
  20+ errors** (`azure-maps-image-exporter.js`,
  `azure-maps-swipe-map.min.js`) — not an efficiency issue directly, but
  worth flagging separately to a maintainer if these are unused/dead code;
  if genuinely unused, removing = pure efficiency win (less JS shipped).
  Not confirmed unused yet — needs an import-graph check before touching.

### LOW / not yet investigated
- Icon bundle `icons-DIjEmjjT.js` = 63KB (23KB gzip) in the post-split
  build — check if `@fluentui/react-icons` is being imported broadly
  (e.g. `import * as Icons`) vs per-icon named imports; broad imports
  defeat tree-shaking. Not yet grep-verified this run.
- hastelib core library not yet scanned in depth for algorithmic
  complexity issues (nested loops found in `embed_buildings.py`,
  `zip_artifacts.py`, `stats.py`, `tbparser.py`, `url_allowlist.py` via a
  static nested-for-loop scan, but all operate on small, bounded
  per-request collections — not confirmed as meaningful energy sinks at
  realistic scale). Revisit if profiling data ever surfaces a hot path
  here.
- `hastelib` conda-based pytest suite not validated to run in this sandbox
  — Task 1 should retry with conda available, or find an alternative
  fast-path (unittest single-file runs per AGENTS.md) for measuring changes
  to core lib code.

## Backlog cursor
Next run should: (1) look at Cosmos DB SELECT * projection narrowing if a
Cosmos emulator test harness exists (MEDIUM), (2) attempt hastelib pytest
validation via conda if available in the runner, (3) do a broader
dead-asset sweep across `ui/src/assets/**` (not just helpDocs) — the
`interactive/` folder find this run suggests there may be other orphaned
assets elsewhere, (4) verify `@fluentui/react-icons` import style
(LOW, tree-shaking check, still unverified), (5) revisit Task 6
(measurement infrastructure) — not yet done in either run.
