# Phase 2 capability

## Selected proximity workflow

The requested workflow buffers **NJ park points**, then identifies intersecting
census tracts. The source is the pinned `park_points.geojson` snapshot: 394
historical GNIS 2016 park locations from NJDEP Land MapServer layer 5. Open-space
polygons from layer 67 remain a separate display layer and must not be substituted
as the buffer input. Points are not verified park entrances or evidence of public
access. Distances describe geometric proximity, not walking distance or service
coverage. Do not sum populations of intersecting tracts as residents served.

Open **Analysis & NJ layers**, choose a distance in metres, and run **Buffer park
points & intersect tracts**. A statewide 500 m scenario selects **790** unique
tracts. Boundary touches count. All NJ points are candidates, including across
county borders; filters restrict target tracts. Changing a filter clears the
operation so it can be rerun for that target set.

## Current implementation status

The pinned snapshot contains **2,181** full-resolution TIGER/Line 2023 NJ tracts
joined one-to-one to ACS 2019–2023 population, income and 90% margins of error.
Density uses TIGER land area, unlike the county map's boundary-area denominator.
27 tracts lack usable income and six lack land area for density. They are gray
No data, excluded from classification, never converted to zero. ACS income
values 2,499/250,001 represent bottom/top coding, not precise incomes. Click a
tract for estimates and MOEs. Style changes metric, palette, opacity and outlines.

County filters and base layer ordering persist. They select whole park features
by county attributes, without clipping, and retain statewide classification.
The derived tract/buffer group is above base thematic layers; live references
are above it with Move to top controls. Points and place labels remain visible.

Refresh with `python scripts/snapshot_nj_tracts.py`, review staged coverage,
missing values and checksums, then promote with
`python scripts/snapshot_nj_tracts.py --promote .web-cache/nj-tracts` and restart.
The county/parks refresh preserves the separately versioned tract snapshot.
Sources: [TIGER/Line 2023](https://www2.census.gov/geo/tiger/TIGER2023/TRACT/)
and [ACS 2023 API](https://api.census.gov/data/2023/acs/acs5).

## Gate contracts

| Gate | Evaluation |
| --- | --- |
| G1 | Actual display CRS; matching projected spatial-join inputs |
| G2 | Valid demographic values, deterministic classification and skew prescriptions |
| G4 | Actual display distortion; separate distance-operation projection report |
| G5 | Opaque demographic palette, including eight-class lightness when density needs eight head/tail classes |
| G6 | Visible renderer elements; separate PNG completeness verdict |
| G7 | Complete valid NJ Point inputs, unique IDs, explicit 1–10,000 m scenario, EPSG:32111, sampled linear error ≤0.1% |
| G8 | Complete valid polygon inputs, matching projected CRS, unique IDs, intersects predicate; deduplicated tract selection |

G7 returns WARN for an exploratory distance; its 10 km ceiling is a service
scope limit, not a scientifically recommended catchment radius. Buffers use 32
segments per quadrant (maximum radial approximation error 0.031%). G8 rejects
incomplete inputs and unsupported predicates. Rejections include prescriptions
and do not produce output geometry.

G4 **rejects Web Mercator for area-comparison display**, and G1 also rejects
its use for density. G1 uses count/ordinal roles for population/income. Verdicts remain
visible: this is an exploratory preview, not publication certification.
Distance calculations use NAD83 / New Jersey (EPSG:32111), with G7's separate
linear-distortion check. A passed calculation check does not certify display.
G5 does not certify transparency, no-data swatches or overlay contrast. G3a/G3b
and block groups remain outside scope. PNG previews lack an exported scale bar
and correctly receive a separate G6 REJECT.

## Additional NJ reference data

The allowlisted catalog includes NJOGIS MOD-IV parcels and NG9-1-1 roads, plus
NJDEP power plants, NHD 2015 waterbodies and FEMA NFHL served by NJDEP. Each links
to its official service and describes its coverage. Parcel fields exclude owner
names and mailing addresses; MOD-IV matches may be incomplete. Parcel outlines
are not surveys. Flood overlays are references, not regulatory determinations.

Zoom to a neighborhood, select a layer and **Load this view**. Each query is
limited to a NJ extent of 0.04 square degrees, 2,000 features and 12 MiB. Count,
pagination and identifier inconsistencies reject the response. No silently
truncated dataset is displayed. Loaded extents stay fixed while panning. Offline
mode disables live references. These layers are excluded from spatial analysis.

Download tract analysis GeoJSON, operation traces, verdicts, PNG previews and
reference snapshots in the panel. Workspace v5 binds both analysis snapshots and
a deterministic result hash, recomputed on import. V2–v4 remain importable.
Live references do not reload on import. Reference downloads include extent,
source, retrieval time, count and checksum. See [workspace contracts](workspace-format.md).

## Verification and limits

`tests/test_phase2.py` tests snapshot coverage, all demographic classifications,
independent brute-force intersection agreement, rejection paths, display gates,
render completeness, workspace result tampering and reference bounds/truncation.
CI runs it with web, private-beta, refresh, workspace, contract and G1/G2/G4/G5/G6
tests, frontend build and Docker build. The original coverage baseline is retained.
One spatial request runs per process; excess requests return 429. This CPU/memory
limit is separate from shared per-user AI quotas. Reference layers use bounded
queries instead of loading millions of parcels into the Starter service.

Local verification on 2026-09-17: the expanded 202-test regression set passed
across the suite and subsequent focused runs, and the TypeScript/Vite build
passed. Browser checks rendered the 500 m / 790-tract scenario and exercised PNG
export with its explicit G6 rejection. Real bounded service queries returned
MOD-IV parcels, roads and flood areas; all five service metadata contracts were
verified. The working tree is served locally on port 8004; Render has not been
updated. A new Linux image build was attempted but blocked by Docker Desktop's
inference-manager socket startup error before the Linux engine became available.
Container verification remains outstanding; no successful build is claimed.
