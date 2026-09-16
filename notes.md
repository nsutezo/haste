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
