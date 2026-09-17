# Module Coverage Ledger

| Module | Blob Hash | Last Inspected (UTC) | Observation |
|--------|-----------|----------------------|-------------|
| hastelib/src/hastegeo/core/utils/assessment.py | 6b3b5638 | 2026-09-17 22:41 | Fused 5-way confusion-matrix computation into one pass (PR #5). Follow-up: `_average_precision` + `_precision_recall_curve` sort the same list independently — hoisting the sort would save one O(n log n) per report (backlog MEDIUM). |
| hastelib/src/hastegeo/core/utils/gdal_security.py | 71515bf4 | 2026-09-17 22:41 | `harden_gdal` builds the driver list with `gdal.GetDriver(i)` twice per iteration (once in the condition, once in the yielded value) — trivial local-var fix, added to backlog MEDIUM. Import-time only, small win. |
| hastelib/src/hastegeo/core/utils/imagery.py | f428d1a4 | 2026-09-17 22:41 | Scanned; heavy GDAL/OpenCV usage but each helper is a thin wrapper around a single external call. No obvious redundant-loop patterns. Would benefit from measurement before optimising. |
| hastelib/src/hastegeo/core/utils/footprints.py | c1882094 | 2026-09-17 22:41 | Scanned intro sections; uses `lru_cache`, pyarrow filters and streaming `RecordBatchReader` — reasonably efficient. Not a promising target this pass. |
| hastelib/src/hastegeo/core/processors/stats.py | 12ebb856 | 2026-09-17 22:41 | Small file. Uses `list(set(...))` dedup of `modelIds` (fine, small collection). Does a linear scan of `summary.projects` to find matching id — bounded (project count is small); not a win. |
