# Data manifest

| File | SHA-256 | Features | Source | Snapshot date |
|---|---|---|---|---|
| `atlanta_tracts_fulton_dekalb.geojson` | `cc95e62ce158dca0daf180514e6223cdb970b76f4609dceb8574c51ed5e03f81` | 530 | TIGERweb Tracts_Blocks layer 4, STATE=13, COUNTY IN (121, 089) | 2026-07-08 |

Regenerate with `python scripts/snapshot_tiger.py` (network required). `scripts/gen_results_panel.py` reads this snapshot by default; pass `--live` to bypass it. If the feature count or hash changes on re-snapshot, the Census service revised the geometry — re-run the results panel and re-verify the published statistics before reusing them.
