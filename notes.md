# Efficiency Improver — Repo Notes (nsutezo/haste)

## Environment gotchas
- `npm ci` fails out of the box: `ui/package-lock.json` resolves packages
  from internal `ms-feed-*.pkgs.visualstudio.com` hosts unreachable from
  this sandbox. Fix locally only (never commit): rewrite those hosts to
  `https://registry.npmjs.org/` in a scratch copy, `npm ci --ignore-scripts`,
  then always `git checkout -- package-lock.json` before finishing.
- `keytar` (transitive dep of `@azure/static-web-apps-cli`) needs
  `libsecret-1` dev headers to compile from source; not available in this
  sandbox and no root/apt access. `--ignore-scripts` avoids the native
  build entirely — fine for `vite build`/`eslint`/`node --test`, since none
  of those need keytar's compiled binding.
- No conda in this sandbox; `hastelib`'s hatch test env is conda-based
  (GDAL/rasterio pinned versions) — could not validate `hatch run
  test:pytest` this run.

## Techniques that worked well
- **Bundle-size proxy metric via `vite build` output**: fast (~1s), no
  server needed, gives per-chunk gzip sizes directly in stdout. Great
  before/after evidence for code-splitting / lazy-loading changes without
  needing a browser or Lighthouse.
- Static nested-for-loop grep scan (indent-based heuristic in Python) is a
  quick way to shortlist O(n²) candidates across a whole Python package
  in one pass; most hits in this repo turned out to be small bounded
  collections (project lists, image layer lists) rather than real hot
  loops — don't assume nested loops = win without checking scale of input.

## Key insight for this repo
- The UI's route table (`AppBody.jsx`) was the single biggest lever found
  so far: one file change, no new dependencies, immediately measurable via
  the existing `vite build` output, zero test breakage. This is the kind
  of change to prioritize each round: high measurable impact, low risk,
  small diff.
- Second run insight: always grep-verify asset references before assuming
  a "large asset" backlog item is purely an image-compression task — the
  HelpDocs `interactive/` folder turned out to be 100% dead code (7.3MB),
  bigger win than optimizing it would have been. Do a `grep -rn <filename>
  ui/src` check for every asset file before spending time re-encoding it.

## Critical process lesson (2026-09-17 run)
- Memory previously claimed a PR for HelpDocs image optimization was
  already created (2026-09-16 entry), but it was NOT — the branch never
  existed remotely and the working tree still had the full 17MB of
  unoptimized/dead assets untouched. **Always cross-check memory's "DONE"
  claims against actual repo state at the start of each run**: check
  `list_pull_requests`/`search_pull_requests` for the claimed branch/PR
  title, and re-check file sizes (`du -sh`) for claimed-optimized
  directories, before skipping a backlog item as already handled. A run
  can fail partway through (e.g., after measurement but before PR
  creation) and still get logged in memory as complete if the writer
  didn't verify the safe-output call actually succeeded.

## Image tooling (no cwebp/pngquant/ImageMagick preinstalled, no sudo)
- This sandbox has no system image tools and no root access
  (`sudo` is blocked: "no new privileges" flag set). System `pip install`
  also fails (`externally-managed-environment`).
- Working approach: `python3 -m venv /tmp/gh-aw/agent/venv && \
  /tmp/gh-aw/agent/venv/bin/pip install Pillow` — gives WebP encode/decode
  (`Image.save(path, "WEBP", quality=82, method=6)`) without touching
  system Python or committing a new dependency. Quality 82 gave 64-91%
  size reduction on documentation screenshots with no visible artifacts
  on manual inspection (no pixel-diff tooling available in this sandbox
  — noted as a proxy limitation).

## 2026-09-19 run — binary-diff patch-size limit (CRITICAL, read before any image/binary PR)
- `create_pull_request` / `push_to_pull_request_branch` are configured
  with `max_patch_size: 4096` (KB) in `.github/workflows/
  efficiency-improver.lock.yml`. This applies to the **unified-diff
  patch size** (`git format-patch`), which inflates binary file changes
  ~1.4-1.6x versus raw byte count (base64 + diff headers). A single
  commit touching several MB of images WILL exceed this — this is
  confirmed root cause of issues #3 and #4 (single ~22MB patch attempts
  across two earlier runs).
- **Always pre-check**: `git format-patch -1 --stdout HEAD -- <paths> |
  wc -c` per candidate file group BEFORE calling create_pull_request.
  Budget commits to ~3.8MB each (safety margin below 4194304 bytes).
- **Fix**: split the same logical change into multiple small commits on
  ONE branch (first-fit-decreasing bin-packing by per-file patch size
  works well — few lines of Python). `create_pull_request` pushes
  whatever commits already exist on the local branch, so this doesn't
  cost extra PR-creation budget. Put deletions bundled with their
  same-size-class replacement additions in the same commit for a
  cleaner diff story; save JSX/import-path updates for the LAST commit
  so the tree stays consistent (buildable) at every intermediate commit.
- Confirmed this workaround succeeds: 7 commits of ~3.7-3.8MB each,
  final `create_pull_request` call returned `"result":"success"` with a
  760KB git-bundle artifact (not a 22MB patch) — the tool bundles the
  whole branch, not just a single squashed patch, once commits are
  small enough individually.

## 2026-09-18 14:47 UTC run — process/tooling lessons
- The efficiency-profiler / verifier tools referenced in earlier memory
  entries (`.github/tools/efficiency-profiler/`, `.github/tools/
  verifier/`) do NOT exist in this sandbox checkout — `find .github`
  shows no `tools/` directory at all. Either they were removed, never
  committed, or are generated per-run by the workflow harness and not
  persisted. Don't assume they exist; check with `find`/`ls` first, and
  fall back to a standalone `time.perf_counter` benchmark script (in
  `/tmp/gh-aw/agent/`, not the repo) if absent — that's still a valid
  proxy-metric measurement, just document the methodology explicitly.
- Rate limiting: `search_pull_requests`/`search_issues` via the GitHub
  MCP bridge can hit a 30-req/short-window cap; back off ~15s and retry,
  or prefer `list_pull_requests`/`issue_read` (non-search) where the
  target number is already known.
- Bundling two small, independent, same-file-family fixes (shared-sort
  hoist + GDAL double-call) into one PR was reasonable here since both
  are tiny, low-risk, and touch adjacent code — but keep genuinely
  unrelated modules in separate PRs per the "small, focused PRs" rule.

- `compute_assessment_report` in `hastegeo.core.utils.assessment` had a
  textbook ES-03/SP-C3 pattern: four generator sums over the same iterable
  plus a materialised `y_pred` list. Fusing them into one loop was a low-
  risk, high-signal win (verifier: -10.7% wall, p=0, large effect).
- Look for `sum(1 for ... if X)` clusters over the same iterable — they
  often collapse to one pass with identity substitutions.
- The efficiency profiler's top-level delta *under-states* real hot-path
  wins whenever the workload includes untouched setup cost (200k dict
  build here was ~35% of wall time and unchanged). Always compare to the
  verifier's targeted benchmark for the "true" delta on the modified path.
- Verifier's test gate is repo-wide — an untouched module that can't
  collect (missing native GDAL/pystac in this sandbox) will fail the
  gate even for a pure-logic change with 16/16 tests passing on the
  changed module. Report both facts honestly; per instructions, the
  verifier verdict is informational, not a merge gate.
- Workload trick: keeping the workload script at an absolute path
  outside the repo (session workspace) lets the profiler run it in both
  baseline and candidate worktrees without needing to seed the file
  into the baseline worktree.
