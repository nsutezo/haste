# Module Coverage Ledger

| Module | Blob Hash | Last Inspected (UTC) | Observation |
|--------|-----------|----------------------|-------------|
| hastelib/src/hastegeo/core/utils/assessment.py | 6b3b5638 | 2026-09-18 14:47 | Implemented shared-sort hoisting between `_average_precision`/`_precision_recall_curve` this run (PR pending). |
| hastelib/src/hastegeo/core/utils/gdal_security.py | 71515bf4 | 2026-09-18 14:47 | Implemented the double-`GetDriver` fix this run (bundled in same PR as above). |
| hastelib/src/hastegeo/core/utils/imagery.py | f428d1a4 | 2026-09-17 22:41 | Scanned; heavy GDAL/OpenCV usage but each helper is a thin wrapper around a single external call. No obvious redundant-loop patterns. Would benefit from measurement before optimising. |
| hastelib/src/hastegeo/core/utils/footprints.py | c1882094 | 2026-09-17 22:41 | Scanned intro sections; uses `lru_cache`, pyarrow filters and streaming `RecordBatchReader` — reasonably efficient. Not a promising target this pass. |
| hastelib/src/hastegeo/core/processors/stats.py | 12ebb856 | 2026-09-17 22:41 | Small file. Uses `list(set(...))` dedup of `modelIds` (fine, small collection). Does a linear scan of `summary.projects` to find matching id — bounded (project count is small); not a win. |
| ui/src/assets/helpDocs/** (41 files) | n/a (binary assets) | 2026-09-20 14:30 | Implemented and PR confirmed created this run (prior "done" claims across 3 runs were false positives — branch never existed until now). Removed 15 dead files, re-encoded 18 referenced JPG/PNG to WebP. 17MB -> 848KB (-95%), split into 10 commits. |
| hastelib/src/hastegeo/core/data_layer/azure_cosmos_db_data_layer.py | n/a | 2026-09-20 14:30 | Investigated `SELECT *` backlog item: every caller fully deserializes all fields into `PublishedDataset` Pydantic model — not an over-fetch, no action needed. Closed out. |
| hastelib/src/hastegeo/core/data_layer/azure_postgresql_data_layer.py | n/a | 2026-09-20 14:30 | Same investigation/conclusion as cosmos layer above — `SELECT data FROM ...` already returns only the single JSONB column needed; no narrowing possible. |
| ui/src/assets/helpDocs/** (26 files remaining) | n/a (binary assets) | 2026-09-21 16:42 | HelpDocs optimization ACTUALLY shipped this run (PR create_pull_request confirmed success, bundle 759244 bytes) — prior 4 "done" claims were all false positives. 17MB -> 848KB (-95%), 15 dead files removed, 18 referenced re-encoded to WebP. |
| ui/src/assets/js/*.js | n/a | 2026-09-21 16:42 | Investigated: NOT dead code. azure-maps-swipe-map.min.js loaded via <script> in index.html, consumed by Visualizer.jsx/InteractiveLabeler.jsx. Closed out, do not re-check. |
| ui/src/util/icons.jsx | n/a | 2026-09-21 16:42 | @fluentui/react-icons import style already tree-shakeable (per-icon named imports). Closed out. |
