# Energy Efficiency Backlog (nsutezo/haste)

Last updated: 2026-09-15 (first run, workflow run 35015265296)

## Completed this run
- [DONE] **Frontend/UI, HIGH** — Route-level code splitting in
  `ui/src/Components/AppBody.jsx`. Converted all routed component static
  imports to `React.lazy()` + `Suspense`. Main entry JS chunk went from
  1,489,465 bytes (406.67 kB gzip) to 119,046 bytes (36.40 kB gzip), a 92%
  reduction. HelpDocs' ~17MB of embedded screenshot images (previously
  reachable from the eager import graph) now only fetch when a user visits
  `/help-docs`. PR created: branch `efficiency/route-level-code-splitting`.

## Open opportunities (not yet implemented)

### HIGH
- **HelpDocs images are unoptimized JPEG/PNG, some multi-MB** (Frontend/UI +
  Data efficiency). `ui/src/assets/helpDocs/**` totals ~17MB; several PNGs
  are 2-2.5MB each (`results-visualizer.png`, `damage-visualizer.png`,
  `labeler-labeled.png`, `labeler-predicted.png`, `building-validation.png`,
  `raw-predictions-layer.png`). These are screenshots — likely reducible by
  50-80% by re-encoding as WebP/AVIF or just re-compressing PNG/JPEG at
  reasonable quality, with no visible quality loss for documentation
  screenshots. Now that route-splitting (see above) means these only load
  on `/help-docs` visits, this is the next logical layer of savings for
  users who *do* visit that route. Needs: visual diff review before/after
  re-encoding, and decide whether to add `<picture>`/WebP fallback or just
  replace source files directly (simpler, no new markup, but loses avif
  option for browsers that support it). Measurement: file size before/after
  re-encode; decode cost is harder to measure without profiling in a real
  browser — note as a proxy limitation in any future PR.

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
Next run should: (1) investigate HelpDocs image re-encoding (HIGH,
straightforward, high-confidence win), (2) look at Cosmos SELECT *
projection narrowing if a Cosmos emulator test harness exists, (3) attempt
hastelib pytest validation via conda if available in the runner.
