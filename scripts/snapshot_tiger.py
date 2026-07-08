#!/usr/bin/env python3
"""Snapshot the Atlanta TIGER tract geometry into data/ with a checksum.

Fixes Fable Review/01_OPERATING_MANUAL.md TD-7: the poster results figure
previously depended on a live TIGERweb query at render time. This script
pins the geometry so `scripts/gen_results_panel.py` reproduces offline.

Usage:  python scripts/snapshot_tiger.py
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
SNAPSHOT = DATA / "atlanta_tracts_fulton_dekalb.geojson"
MANIFEST = DATA / "MANIFEST.md"

TIGER_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "Tracts_Blocks/MapServer/4/query"
    "?where=STATE%3D%2713%27+AND+COUNTY+IN+%28%27121%27%2C%27089%27%29"
    "&outFields=GEOID%2CNAME%2CSTATE%2CCOUNTY%2CTRACT"
    "&f=geojson&outSR=4326&resultRecordCount=2000"
)


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    print("Downloading Census TIGER tracts (Fulton + DeKalb, GA) ...")
    req = urllib.request.Request(TIGER_URL, headers={"User-Agent": "CartoLLM/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()

    payload = json.loads(raw.decode("utf-8"))
    n_features = len(payload.get("features", []))
    print(f"  -> {n_features} features")

    # Canonicalize: stable key order, no float mangling, LF newline.
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    SNAPSHOT.write_text(canonical, encoding="utf-8", newline="\n")
    sha = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()

    MANIFEST.write_text(
        "# Data manifest\n\n"
        "| File | SHA-256 | Features | Source | Snapshot date |\n"
        "|---|---|---|---|---|\n"
        f"| `{SNAPSHOT.name}` | `{sha}` | {n_features} | "
        f"TIGERweb Tracts_Blocks layer 4, STATE=13, COUNTY IN (121, 089) | {date.today().isoformat()} |\n\n"
        "Regenerate with `python scripts/snapshot_tiger.py` (network required). "
        "`scripts/gen_results_panel.py` reads this snapshot by default; pass "
        "`--live` to bypass it. If the feature count or hash changes on "
        "re-snapshot, the Census service revised the geometry — re-run the "
        "results panel and re-verify the published statistics before reusing "
        "them.\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"  -> {SNAPSHOT.relative_to(REPO)}")
    print(f"  -> SHA-256 {sha}")
    print(f"  -> {MANIFEST.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
