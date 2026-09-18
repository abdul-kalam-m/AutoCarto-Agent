"""Stage full-resolution TIGER/Line 2023 NJ tracts joined to ACS 2019–2023.

Review the staged manifest and use --promote to install it. No simplification
is applied to the analysis geometry. Requires the geo and web extras.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd

from snapshot_nj_web import ACS, DEST, fetch
sys.path.insert(0, str(DEST.parents[2]))
from autocarto.env import get_key

TIGER = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_34_tract.zip"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".web-cache/nj-tracts"))
    parser.add_argument("--promote", type=Path)
    args = parser.parse_args()
    if args.promote:
        raw = (args.promote / "tracts.geojson").read_bytes()
        entry = json.loads((args.promote / "tracts-manifest.json").read_text())
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("Tract checksum mismatch")
        manifest = json.loads((DEST / "manifest.json").read_text())
        manifest["files"]["tracts.geojson"] = entry
        manifest["sources"]["tracts"] = TIGER
        manifest["coverage"]["tracts"] = entry["coverage"]
        shutil.copyfile(args.promote / "tracts.geojson", DEST / "tracts.geojson")
        (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print("Promoted tract snapshot", entry["features"], entry["sha256"])
        return
    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output / "tracts.zip"
    if not archive.exists():
        urllib.request.urlretrieve(TIGER, archive)
    frame = gpd.read_file(archive).to_crs(4326)
    rows = fetch(ACS, {"get": "NAME,B01003_001E,B01003_001M,B19013_001E,B19013_001M", "for": "tract:*", "in": "state:34 county:*", "key": get_key("CENSUS_API_KEY")})
    records = [dict(zip(rows[0], row)) for row in rows[1:]]
    values = {r["state"] + r["county"] + r["tract"]: r for r in records}
    if set(frame.GEOID) != set(values) or len(frame) != len(values) or not frame.geometry.is_valid.all():
        raise ValueError("Tract geometry/ACS coverage mismatch or invalid geometry; review before promotion")
    features = []
    def estimate(row, key):
        value = int(row[key])
        return value if value >= 0 else None
    from shapely.geometry import mapping
    for _, row in frame.sort_values("GEOID").iterrows():
        acs = values[row.GEOID]
        population = estimate(acs, "B01003_001E")
        area = int(row.ALAND) / 2589988.110336
        properties = {"id": row.GEOID, "name": acs["NAME"], "county_id": row.GEOID[:5],
                      "population": population, "income": estimate(acs, "B19013_001E"),
                      "population_moe": estimate(acs, "B01003_001M"), "income_moe": estimate(acs, "B19013_001M"),
                      "area_sq_miles": area, "density": population / area if population is not None and area > 0 else None}
        features.append({"type": "Feature", "id": row.GEOID, "properties": properties, "geometry": mapping(row.geometry)})
    raw = json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":"), allow_nan=False).encode()
    digest = hashlib.sha256(raw).hexdigest()
    entry = {"sha256": digest, "version_id": "nj-tracts-tiger2023-acs2023-v1-" + digest[:16], "features": len(features),
             "retrieved_at": datetime.now(timezone.utc).isoformat(), "geometry_source": TIGER, "demographics_source": ACS,
             "coverage": "Full-resolution TIGER/Line 2023 NJ tracts, ACS 2019–2023 estimates and 90% MOEs. Density uses TIGER land area. Negative ACS sentinels become null (unavailable/suppressed); zero population is retained. Geometric proximity is not access or population served.",
             "missing": {key: sum(f["properties"][key] is None for f in features) for key in ("population", "income", "density")}}
    (args.output / "tracts.geojson").write_bytes(raw)
    (args.output / "tracts-manifest.json").write_text(json.dumps(entry, indent=2))
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
