# Workspace and trace contracts

The canonical [schema.json](../src/autocarto/traces/schema.json) is a packaged,
offline JSON Schema Draft 2020-12 contract. It was defined before import code.
`GET /api/workspace/schema` serves the same file. No remote schema resolution,
dataset URL fetch, LLM call, or execution of imported code is performed.

| Kind | Version | Purpose |
| --- | --- | --- |
| `workspace` | 2 | Restorable UI state with dataset versions and validation trace |
| `workspace` | 3 | Adds historical park point visibility and snapshot binding |
| `workspace` | 4 | Adds county filters and configurable drawing order |
| `workspace` | 5 | Adds tract snapshot, proximity inputs/result hash and live reference selections |
| `spatial-operation-trace` | 1 | Buffer/intersection inputs, verdicts, matched tract IDs and provenance |
| `web-map-trace` | 1 | County G2/G5 and open-space categorical G5 audit plans |
| `orchestrator-trace` | 1 | Existing CLI proposal/gate iterations and render outcome |

Workspace v2 records settings, layer visibility, opacity, outlines, basemap,
camera center/zoom/bearing/pitch, selected county, and conversation in the `messages` field. Its
`datasets` map binds both datasets by version ID and full SHA-256. Its `trace`
contains the actual computed breaks, palettes, gate decisions and plan IDs.
Optional AI mode is deliberately not restored: importing a file cannot turn
on model calls. Strings in `messages` are restored as text, never executed.

Import uses `POST /api/workspace/import`. It rejects unknown fields or versions,
nonfinite numbers, duplicate keys, excessive nesting, and files above 1 MiB.
It verifies dataset versions, selected county, and recomputes the plans from
the requested settings. A mismatched saved trace is an error, not authority
to override the engine. All checks complete before any UI state changes.
API-level round trips preserve the document; browser camera values can show
normal floating-point differences after MapLibre restores a view.

An export is also validated by the same endpoint before download. Files
contain a maximum of 200 messages (8,000 characters each). Oversized history
is rejected rather than silently truncated. PNG and GeoJSON are exports, not
workspace import formats. Workspace v4 stores drawing order bottom to top in
`layer_order`, with each layer appearing exactly once. `county_filter` stores
unique county FIPS IDs; an empty array displays all counties. Filtering selects
whole features by county attributes, without clipping geometries or changing
the statewide classification breaks. Multi-county park features remain whole
when any county matches; features without a matching county attribute are hidden.

## Compatibility

The pre-schema `version: 1` web file was an audit-only record: it omitted the
camera and county visibility and referenced the retired GNIS point dataset.
It is explicitly rejected rather than silently assigning the new polygon
data or inventing missing state. Retain it as an audit artifact. New exports
use workspace v5; they require the exact pinned datasets and matching engine
results. Restore earlier snapshots from version control for old v2 files.

Any future incompatible format change needs a new version plus an explicit,
tested migration. Keep older schema definitions when a supported migration
is added. Unknown future versions always fail with an actionable message.
Historical demo JSON files are unchanged and are not claimed to conform to
the new orchestrator schema; new `autocarto run` traces carry kind/version.
CLI `trace_json()` validates its output before serialization.

## Validate and compare

```sh
python -m autocarto.traces validate cartollm-workspace.json
python -m autocarto.traces diff before.json after.json
python -m autocarto.traces diff trace-a.json trace-b.json --ignore-timing
```

The diff emits sorted JSON-pointer paths with added, removed, or changed
values. Array order and numeric values matter; JSON numbers `1` and `1.0`
compare equally, booleans do not. No numeric tolerance is applied. Exit codes
are 0 for valid/equal, 1 for differences, and 2 for invalid files or I/O errors.
`--ignore-timing` ignores only the five named timing fields already used by
the repository's trace tests. Dataset versions, hashes, and gate decisions
are always compared. Both files must conform to a supported schema.

## Phase 0 acceptance — 2026-09-16

The browser exported an income map focused on Essex County with satellite
imagery, open space enabled, and a conversation. After changing the metric,
basemap, view, and layer visibility, importing and re-exporting that file
produced an empty structural diff (`[]`, exit 0). The polygon popup and PNG
categorical legend/source attribution were also inspected.

Final regression: **347 passed, 30 skipped**, with the frontend TypeScript and
production build passing. The pre-change coverage measurement is preserved
separately in [coverage-baseline.md](coverage-baseline.md).

Workspace v3 adds required `park_points` visibility and a `datasets.park_points`
version/checksum binding. The browser exports v5. V2 remains importable unchanged;
its missing point layer opens disabled, and the next browser save writes v5 with
the current point snapshot explicitly bound. Existing county/polygon bindings
and traces must still match exactly. All versions store chat in `messages`.
V2 and v3 open with all counties and the default drawing order (counties, open
space, then park points). Their existing trace format is preserved.

V5 adds `phase2`: tract visibility, `distance_m`, `result_id`, and selected live
reference IDs in drawing order. It binds the tract snapshot. Import recomputes
proximity and checks its result hash, including gate verdicts and matched IDs.
Changing county filters clears proximity; rerun it for the new target tract set.
All NJ park points remain candidates across borders. V2/v3/v4 remain supported.
Live references are never fetched on import; their selections restore but the
user must load an extent again. Downloaded reference GeoJSON carries retrieval
time, extent, source, count and checksum; it is not an accepted analysis input.
