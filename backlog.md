# Energy Efficiency Backlog (nsutezo/haste)

Last updated: 2026-09-17 (third run, workflow run 35239489111)

## IMPORTANT correction from this run
Previous memory (2026-09-16 run) claimed a PR titled
`perf(ui): optimize HelpDocs images and remove dead assets` had already
been created on branch `efficiency/optimize-helpdocs-images`. This was
NOT true — verified via `list_pull_requests`/`search_pull_requests`
that only PR #1 (route-level code splitting) existed, and the
`ui/src/assets/helpDocs` tree was still 17MB/untouched in the working
tree at the start of this run. **Do not fully trust prior "DONE"
claims in memory without cross-checking actual repo/PR state at the
start of every run** — re-verify file sizes / PR existence before
skipping a backlog item as complete.

## Completed this run (2026-09-17, run 35239489111)
- [DONE, RE-VERIFIED-AND-ACTUALLY-SHIPPED] **Frontend/UI + Data, HIGH**
  — HelpDocs image optimization. Branch
  `efficiency/optimize-helpdocs-images`, PR created this run (title
  `[efficiency-improver] perf(ui): optimize HelpDocs images and remove
  dead assets`). Two sub-changes:
  1. Re-encoded 12 referenced-but-unoptimized images (results-visualizer,
     8 labeling comparison JPEGs, 3 model-catalog JPEGs) to WebP q=82
     via Pillow. 5,236,693 -> 719,710 bytes (-86.3%).
  2. Deleted 12 files (~11.8MB) of **completely dead assets** never
     imported anywhere in ui/src: the entire
     `ui/src/assets/helpDocs/interactive/` folder (9 files, 7.3MB) plus
     3 orphaned `results/` images (damage-visualizer.png,
     raw-predictions-layer.png, results-menu.png). Confirmed via grep
     across all `.jsx`/`.js` in ui/src that no import references these
     filenames; matching filenames exist only in the separate
     `docs/_static/usage/` doc-site copies.
  Net: ui/src/assets/helpDocs 17MB -> 1.1MB (-94%). Verified via
  `npm run build` (webp assets bundle correctly into dist/), eslint
  (9 pre-existing errors identical to main via git stash diff, 0 new),
  and all 4 existing node --test suites (66/66 pass).
  Tooling: throwaway Python venv (`python3 -m venv` + `pip install
  Pillow`), not committed, no new project dependency.

## Completed previously (still open, unmerged as of this run)
- [PR OPEN] **Frontend/UI, HIGH** — Route-level code splitting in
  `ui/src/Components/AppBody.jsx` (PR #1, draft, state=open,
  mergeable_state=unstable as of this run — no action taken this run,
  no new CI failures or comments observed needing a response).

## Open opportunities (not yet implemented)

### MEDIUM
- **Azure Cosmos DB `SELECT *` queries** in
  `hastelib/src/hastegeo/core/data_layer/azure_cosmos_db_data_layer.py`
  (`load_all`, `load_all_from_partition`, `delete_all_from_partition`,
  `load_bounded`). Still not investigated — needs field-usage check in
  `hastegeo.core.processors.metadata.py` before narrowing SELECT
  projections. Estimated impact: MEDIUM (Cosmos is one of several
  data-layer backends).
- **Vendored third-party JS files under `ui/src/assets/js/`** fail lint
  with 20+ errors (`azure-maps-image-exporter.js`,
  `azure-maps-swipe-map.min.js`) — not confirmed unused yet, needs an
  import-graph check. If unused, removal = pure win.

### LOW / not yet investigated
- Icon bundle `icons-DIjEmjjT.js` ~63KB (23KB gzip) — check if
  `@fluentui/react-icons` is imported broadly (`import * as Icons`) vs
  per-icon named imports; still not grep-verified.
- hastelib core library nested-loop scan done previously (embed_buildings.py,
  zip_artifacts.py, stats.py, tbparser.py, url_allowlist.py) — all appear
  bounded/small-scale, not confirmed hot paths. Revisit only if profiling
  data surfaces.
- `hastelib` conda-based pytest suite still not validated in this sandbox
  (no conda, no network to conda channels). Task 1 should retry if conda
  ever becomes available, or investigate unittest single-file runs per
  AGENTS.md for incremental validation of hastelib changes.
- Broader dead-asset sweep across `ui/src/assets/**` beyond helpDocs —
  not yet done this run; the helpDocs/interactive/ find suggests other
  orphaned assets may exist elsewhere in the tree (e.g. `ui/src/assets/js/`,
  other doc/screenshot folders).

## Backlog cursor
Next run should: (1) verify PR #1 and the new HelpDocs images PR for CI
status / maintainer comments (Task 4), (2) do the broader dead-asset
sweep across `ui/src/assets/**` (still not done — 3 runs in a row now),
(3) look at Cosmos DB SELECT * projection narrowing (MEDIUM, needs field-
usage investigation first), (4) verify `@fluentui/react-icons` import
style (LOW, tree-shaking check), (5) Task 6 (measurement infrastructure)
— not yet done in any of the 3 runs so far, should be prioritized soon.
