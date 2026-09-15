# Validated Build/Test/Lint Commands (nsutezo/haste)

## UI (ui/)
- Install (network-restricted envs): the committed `package-lock.json` points
  at internal Azure DevOps feed hosts (`ms-feed-*.pkgs.visualstudio.com`)
  which are unreachable from sandboxed CI-like environments. Workaround for
  local investigation only (NEVER commit): `sed -i -E
  's#https://ms-feed-[0-9]+\.pkgs\.visualstudio\.com/1es-public/_packaging/npm-public/npm/registry/#https://registry.npmjs.org/#g'
  package-lock.json` then `npm ci --ignore-scripts` (the `--ignore-scripts`
  avoids a `keytar`/`libsecret-1` native build failure from the SWA CLI dep,
  unrelated to app code). Always `git checkout -- package-lock.json`
  afterwards.
- Build: `npm run build` (vite build, ~1s, target es2020). Prints per-chunk
  gzip sizes — good baseline/after evidence source for bundle-size proxy
  metric.
- Lint: `npm run lint` (eslint, max-warnings 0). Repo already has ~220
  pre-existing lint errors unrelated to any single change (mostly
  no-unused-vars, some vendored js files) — lint the specific changed
  file with `npx eslint path/to/file.jsx` to avoid noise.
- Unit tests (node --test, no framework needed):
  - `npm run test:interactive-labeler`
  - `npm run test:ongoing-jobs`
  - `npm run test:label-store`
  - `npm run test:validation-config`
  All passed as of 2026-09-15.
- No Playwright/e2e config found yet in this pass.

## hastelib (core Python library)
- Build: `cd hastelib && hatch build -t wheel`
- Test: `cd hastelib && hatch run test:pytest` — NOTE: `hatch.envs.test` is a
  **conda** environment (environment-file dev_env.yml) with GDAL/rasterio
  pinned; not yet validated to run in this sandbox (no conda, no network
  access to conda channels in a quick check). Treat as unvalidated until a
  future run confirms it works, or investigate `PYTHONPATH=$PWD/hastelib/src
  python -m unittest hastelib.tests.core.utils.test_<name>` per AGENTS.md for
  single-file runs without the conda env.

## api/
- Not yet explored in depth (function_app.py local run needs
  `func host start`, Azure Functions Core Tools — not validated in this
  sandbox).
