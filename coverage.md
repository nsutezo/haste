# Module Coverage Ledger

| Module | Blob Hash | Last Inspected (UTC) | Observation |
|--------|-----------|----------------------|-------------|
| hastelib/src/hastegeo/core/utils/assessment.py | 6b3b5638 | 2026-09-18 14:47 | Implemented shared-sort hoisting between `_average_precision`/`_precision_recall_curve` this run (PR pending). |
| hastelib/src/hastegeo/core/utils/gdal_security.py | 71515bf4 | 2026-09-18 14:47 | Implemented the double-`GetDriver` fix this run (bundled in same PR as above). |
| hastelib/src/hastegeo/core/utils/imagery.py | f428d1a4 | 2026-09-17 22:41 | Scanned; heavy GDAL/OpenCV usage but each helper is a thin wrapper around a single external call. No obvious redundant-loop patterns. Would benefit from measurement before optimising. |
| hastelib/src/hastegeo/core/utils/footprints.py | c1882094 | 2026-09-17 22:41 | Scanned intro sections; uses `lru_cache`, pyarrow filters and streaming `RecordBatchReader` — reasonably efficient. Not a promising target this pass. |
| hastelib/src/hastegeo/core/processors/stats.py | 12ebb856 | 2026-09-17 22:41 | Small file. Uses `list(set(...))` dedup of `modelIds` (fine, small collection). Does a linear scan of `summary.projects` to find matching id — bounded (project count is small); not a win. |
| ui/src/assets/helpDocs/** (41 files) | n/a (binary assets) | 2026-09-19 14:xx | Implemented this run: removed 15 dead files (interactive/ + 6 more PNGs), re-encoded 18 referenced JPG/PNG to WebP. 17MB -> 848KB. PR pending (split into 7 commits for patch-size limit). |
