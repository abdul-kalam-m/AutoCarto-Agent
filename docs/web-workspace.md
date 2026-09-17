# New Jersey web workspace

The web application adds an interactive React / TypeScript / MapLibre workspace
to the existing Python project. FastAPI serves the API and the compiled app from
one origin. It has no database or GIS service dependency at runtime: the small NJ
catalog is packaged as verified GeoJSON snapshots.

## Run locally

Use Python 3.11+ and Node 22+. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -c constraints-ci.txt -e '.[web]'
cd web
npm ci
npm run build
cd ..
autocarto-web
```

Open http://127.0.0.1:8000. The app binds to loopback by default.
For frontend development run `npm run dev` inside `web` with the API running;
Vite proxies `/api` to port 8000. Set `HOST` / `PORT` to override the API listener.

On this Windows machine, Application Control blocked the newer resolved
matplotlib and pyproj wheels. To reproduce the working environment, replace
the `pip install` command above with this command (these two versions are not
pinned in `constraints-ci.txt`):

```powershell
python -m pip install -c constraints-ci.txt -e '.[web]' 'matplotlib==3.10.3' 'pyproj==3.7.1'
```

No operating-system security settings were changed.

## What works

- Interactive county choropleths for population, density, and household income.
- Optional 376 NJDEP state-owned open-space polygons, clickable access/use
  details and facility links, county details, and a sortable county table.
- Guided chat commands and optional NVIDIA LLM intent parsing using the existing
  provider transport. The AI switch is available when `NVIDIA_API_KEY` is set
  on the server (or in the existing gitignored `.env`). It defaults to guided
  mode so normal exploration does not make paid model calls.
  The web adapter defaults to NVIDIA Nemotron 3.5 Lightning; override with
  `AUTOCARTO_WEB_MODEL`. The original CLI model setting is unchanged. The
  legacy Llama 3.1 70B endpoint returned HTTP 410 during integration testing.
  A live structured-intent check passed against Lightning; the provider took
  approximately 42 seconds on that run. The server allows 60 seconds of socket
  inactivity and the browser allows 90 seconds per request.
- Four palette requests, classification requests, opacity, outlines, basemaps,
  map navigation, and county focus.
- Browser-local style persistence; PNG, GeoJSON, and versioned workspace/trace
  JSON export. Import workspace v2 from the Export map dialog to restore the
  view, selected county, visibility, styles, basemap, and conversation.
  [Workspace and trace contracts](workspace-format.md) describe compatibility,
  exact dataset binding, validation, and the structural diff command.
- Explicit unsupported-request and provider-failure responses; there is no
  generated-code execution route or arbitrary source URL fetch route.

Example requests: `Show population density across New Jersey`, `Map household
income`, `Add parks`, `Hide parks`, `Make the map purple`, `Use natural breaks`,
`Show income in Essex County`, `Reset to statewide`.

Runtime limits: POST requests with a declared `Content-Length` over 16 KiB
(16,384 bytes) return HTTP 413; each API process admits at most two concurrent
chat requests (guided or AI), returning HTTP 429 with "The agent is busy.
Try again shortly." when both slots are occupied. The workspace-import endpoint
has a separate 1 MiB limit, enforced while streaming even without a declared
length; its schema allows at most 200 messages of 8,000 characters each.

## Deterministic validation and limitations

The web adapter reuses **G2 classification** and **G5 palette accessibility**.
Actual values stay in Python. The LLM receives `SemanticContext` metadata and
the user's request, returning an allowlisted command. The server computes and
validates breaks, applies prescriptions, and emits a map plan with a stable
hash and full trace. Client styling cannot submit custom break values. Failed
LLM calls do not fall back to a different variable. The renderer uses the same
right-inclusive class convention as G2, including exact-boundary values.

This is an exploratory **Web Mercator** view, not the CLI's fully validated
publication output. G1, G3a/G3b, G4 and G6 are not run. G5 checks the opaque
palette, not colors blended with a basemap at reduced opacity. These limits
are shown in the validation dialog. Count maps are available for exploration;
population density is the default. Bivariate analysis, numeric filtering,
buffers and neighborhood/tract analysis are not implemented. Focusing on a
county zooms the view; it does not change statewide classification.

Open space uses a separate opaque categorical fill on `FEATURE_CLASS`. G5
checks every pair in its fixed palette and legend text contrast; categories
are not ranked. The pinned snapshot has 375 `Open Space` features and one
missing class, explicitly shown as `Unspecified`. This does not certify
contrast against every basemap or overlap with the county layer.

`AUTOCARTO_OFFLINE=1` disables AI and external basemap tiles; packaged data
still loads locally. Local fonts are bundled. Normal basemaps load tiles from
Esri public basemap services, with on-screen and PNG-export attribution.

## Data provenance

- [NJOGIS county boundaries](https://maps.nj.gov/arcgis/rest/services/Framework/Government_Boundaries/MapServer/1): all 21 counties, simplified to 0.0005 degrees for web display.
- [Census ACS 2019–2023 5-year estimates](https://api.census.gov/data/2023/acs/acs5): `B01003_001E/M` population and `B19013_001E/M` median household income and their 90% margins of error. Dollar estimates are in 2023 inflation-adjusted dollars.
- [NJDEP Open Space (State Owned) Generalized, layer 67](https://mapsdep.nj.gov/arcgis/rest/services/Features/Land/MapServer/67): 376 polygons retrieved 2026-09-16. This covers NJDEP-administered state-owned open space, not all municipal, county, federal or private parks. `USE_DESIGNATION`, `PUBLIC_ACCESS`, and `FACILITY_URL` are retained. Public access is `Yes` for 264 features, `No` for 24, and unspecified for 88; 42 have no facility link. Popups report the source designation and link to operating information where available.

Density is population divided by **NJOGIS boundary area**, not Census land
area. Do not compare it directly with Census land-only density without
recomputing the denominator. Counties join by five-digit FIPS, with all 21
matches required. Negative ACS margin-of-error sentinels are retained in
exports and omitted as numeric error bounds in the UI.

Refresh deliberately, with `CENSUS_API_KEY` configured and the `geo` extra
installed (`python -m pip install -c constraints-ci.txt -e '.[web,geo]'`;
include the Windows wheel pins above where needed):

```powershell
python scripts/snapshot_nj_web.py --output .web-cache/nj-snapshot
# Review staged counts, fields, geometry, categories, and manifest changes.
python scripts/snapshot_nj_web.py --promote .web-cache/nj-snapshot
python -m pytest tests/test_web.py tests/test_workspace.py tests/test_snapshot_nj_web.py
```

The first command only stages files; the second promotes those exact bytes
without another network fetch, after checking their hashes. Commit both
GeoJSON files and the manifest together, then restart the API. There is no
scheduled or startup refresh. Keep previous snapshots in version control so
older workspaces can be opened against their exact data.

Manifest v2 contains per-dataset content-derived version IDs, full SHA-256
checksums, coverage notes, retrieval time, pipeline version, and source update
metadata. A retrieval date is not a claim that every record was updated that
day. County bytes are unchanged by this migration. For parks, 17 invalid source
features were repaired with Shapely `make_valid` (polygonal components retained)
before topology-preserving simplification at 0.0001 degrees; all 376 output
geometries are valid. These are generalized exploration boundaries, not tax
parcels or survey geometry. New category values require palette review and G5
validation before use.

`park_plan()` deliberately fails closed if an NJDEP refresh introduces an
unrecognised `FEATURE_CLASS`: "New NJDEP FEATURE_CLASS values require a
reviewed categorical palette." Review the new categories, extend the explicit
palette, and rerun G5 before promoting the refresh. Nominal classes have no
meaningful ordering, so the check uses every pairwise color combination,
not merely adjacent entries in a sequential ramp. Unknown categories never
receive an implicitly approved fallback color.

## Container and cloud path

```sh
docker compose -f compose.web.yml up --build
# or
docker build -f Dockerfile.web -t cartollm-web .
docker run --rm -p 127.0.0.1:8000:8000 --env NVIDIA_API_KEY cartollm-web
```

The multi-stage image builds the frontend and runs the service as a non-root
user. It supports a platform-provided `PORT`, exposes `/api/health`, and keeps
map styles in browser storage; workspace files carry the full restorable state.
The same image can run on a container host.
Secrets must be injected at runtime; `.env` is excluded from the build context.

No cloud resources are provisioned. Before a public multi-user deployment,
put authentication and per-user quotas in front of the API (especially the
LLM endpoint), choose persistent project storage, and add hosted sharing.
For larger NJ datasets, add ingestion jobs and object storage / vector tiles;
the pinned county-and-open-space GeoJSON catalog is intentionally small.

## Verify

```sh
python -m pip install -c constraints-ci.txt -e '.[web,dev,geo]'
python -m pytest tests/test_web.py tests/test_workspace.py tests/test_snapshot_nj_web.py tests/gates/test_gate2.py tests/gates/test_gate5.py tests/test_contracts.py
cd web
npm run build
```

API docs are available at `/docs`. The web tests cover every combination of
dataset, palette and classification, snapshot checksums, unsupported commands,
schema-only model context, offline mode, and validation at the API boundary.
The [Web workspace CI workflow](../.github/workflows/web.yml) runs the same
web, workspace, snapshot, G2, G5, and contract tests plus a clean frontend install and production
build on Ubuntu with Python 3.12 and Node 22.
The [measured pre-Phase-0 coverage baseline](coverage-baseline.md) records the
full-suite command, results, and the gate/sandbox percentages.

Private beta: see [private-beta.md](private-beta.md) for server accounts,
autosave, shared quotas, PostgreSQL, monitoring, and the Render deployment budget.
Historical GNIS park points are available as a separate map toggle. They retain
2016 provenance and the public-access disclaimer; they do not replace layer-67
polygons or inherit their categorical G5 claim.
