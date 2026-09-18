"""Refresh the pinned web catalog from NJOGIS, Census ACS, and NJDEP.

Run from the repository root. Requires CENSUS_API_KEY in .env or the
environment; credentials never enter the snapshot or its source URLs.
"""
from __future__ import annotations

import hashlib
import argparse
import json
import shutil
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from shapely import make_valid, union_all
from shapely.geometry import mapping, shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autocarto.env import get_key

DEST = Path(__file__).resolve().parents[1] / "src/autocarto/web/data"
COUNTIES = "https://maps.nj.gov/arcgis/rest/services/Framework/Government_Boundaries/MapServer/1"
PARKS = "https://mapsdep.nj.gov/arcgis/rest/services/Features/Land/MapServer/67"
PARK_POINTS = "https://mapsdep.nj.gov/arcgis/rest/services/Features/Land/MapServer/5"
ACS = "https://api.census.gov/data/2023/acs/acs5"


def fetch(url, params):
    request = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "CartoLLM/0.1"})
    # Avoid leaking the Census key through exception URLs.
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.load(response)
    except Exception:
        raise RuntimeError(f"Could not read {url}; check connectivity and API credentials.") from None


def arcgis(url, fields, simplify=None):
    params = dict(where="1=1", outFields=fields, outSR=4326, f="geojson", orderByFields="OBJECTID", resultRecordCount=1000)
    if simplify:
        params.update(maxAllowableOffset=simplify, geometryPrecision=5)
    features = []
    while True:
        page = fetch(url + "/query", {**params, "resultOffset": len(features)})
        if "error" in page or "features" not in page:
            raise RuntimeError(f"Invalid ArcGIS response from {url}")
        features.extend(page["features"])
        if not page.get("exceededTransferLimit") and len(page["features"]) < 1000:
            break
        if not page["features"]:
            raise RuntimeError("ArcGIS pagination made no progress")
    return {"type": "FeatureCollection", "features": features}


def add_points(staged, manifest):
    collection = arcgis(PARK_POINTS, "OBJECTID,NAME,TYPE,TOWNSHIP,COUNTY")
    for feature in collection["features"]:
        props = feature["properties"]
        if not feature["geometry"] or feature["geometry"]["type"] != "Point":
            raise ValueError("Historical park locations must be points")
        feature["id"] = str(props["OBJECTID"])
        feature["properties"] = {"id": feature["id"], "name": props["NAME"], "type": props["TYPE"], "township": props["TOWNSHIP"], "county": props["COUNTY"]}
    collection["features"].sort(key=lambda f: f["id"])
    count = fetch(PARK_POINTS + "/query", {"where": "1=1", "returnCountOnly": "true", "f": "json"})["count"]
    if not count or len(collection["features"]) != count or len({f["id"] for f in collection["features"]}) != count:
        raise ValueError("Historical park count/identifiers do not match source")
    raw = json.dumps(collection, separators=(",", ":"), ensure_ascii=False).encode()
    (staged / "park_points.geojson").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    manifest["files"]["park_points.geojson"] = {"sha256": digest, "version_id": f"njdep-gnis2016-v1-{digest[:16]}", "features": count, "retrieved_at": datetime.now(timezone.utc).isoformat()}
    manifest["sources"]["park_points"] = PARK_POINTS
    manifest["coverage"]["park_points"] = "Historical GNIS 2016 named park locations, not park boundaries or entrances. Public access is not verified; these points are separate from current state-owned open-space polygons."
    manifest["refresh_policy"] = "Stage, compare counts/coverage/categories/checksums, review geometries, test, then explicitly promote and commit every GeoJSON with the manifest. Restart API. Version IDs change with content; imports never substitute a different snapshot."


def promote(staged):
    manifest = json.loads((staged / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != 2 or manifest["sources"]["parks"] != PARKS:
        raise ValueError("Only a reviewed layer-67 manifest v2 can be promoted")
    names = ["counties.geojson", "parks.geojson"] + [name for name in ("park_points.geojson", "tracts.geojson") if name in manifest["files"]]
    if (DEST / "tracts.geojson").exists() and "tracts.geojson" not in names:
        raise ValueError("Staging manifest omits the installed tract snapshot; preserve it before promotion")
    for name in names:
        raw = (staged / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest["files"][name]["sha256"]:
            raise ValueError(f"Checksum mismatch: {name}")
    DEST.mkdir(parents=True, exist_ok=True)
    for name in names + ["manifest.json"]:
        shutil.copyfile(staged / name, DEST / name)
    print("Promoted reviewed snapshot. Restart the API and run tests/test_web.py.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEST.parents[3] / ".web-cache/nj-snapshot")
    parser.add_argument("--promote", type=Path, help="Promote an already reviewed staging directory without network access")
    parser.add_argument("--points-only", action="store_true", help="Preserve county/polygon snapshots and stage historical GNIS park points")
    args = parser.parse_args()
    if args.promote:
        promote(args.promote.resolve())
        return
    if args.output.resolve() == DEST.resolve():
        raise ValueError("Stage elsewhere, review the diff, then use --promote")
    if args.points_only:
        args.output.mkdir(parents=True, exist_ok=True)
        manifest = json.loads((DEST / "manifest.json").read_text(encoding="utf-8"))
        for name in ("counties.geojson", "parks.geojson", *(["tracts.geojson"] if "tracts.geojson" in manifest["files"] else [])):
            shutil.copyfile(DEST / name, args.output / name)
        add_points(args.output, manifest)
        (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(json.dumps(manifest["files"]["park_points.geojson"]))
        return
    counties = arcgis(COUNTIES, "OBJECTID,COUNTY,FIPSSTCO,SQ_MILES", 0.0005)
    rows = fetch(ACS, {"get": "NAME,B01003_001E,B01003_001M,B19013_001E,B19013_001M", "for": "county:*", "in": "state:34", "key": get_key("CENSUS_API_KEY")})
    values = {row[-2] + row[-1]: dict(zip(rows[0], row)) for row in rows[1:]}
    assert len(counties["features"]) == len(values) == 21
    for feature in counties["features"]:
        p = feature["properties"]
        row = values[p["FIPSSTCO"]]
        population = int(row["B01003_001E"])
        income = int(row["B19013_001E"])
        assert population > 0 and income > 0 and p["SQ_MILES"] > 0
        feature["id"] = p["FIPSSTCO"]
        feature["properties"] = {
            "id": p["FIPSSTCO"], "name": p["COUNTY"].title(),
            "population": population, "income": income,
            "population_moe": int(row["B01003_001M"]), "income_moe": int(row["B19013_001M"]),
            "area_sq_miles": round(p["SQ_MILES"], 3),
            "density": round(population / p["SQ_MILES"], 2),
        }
    counties["features"].sort(key=lambda f: f["id"])
    metadata = fetch(PARKS, {"f": "json"})
    if metadata.get("geometryType") != "esriGeometryPolygon":
        raise ValueError("NJDEP layer 67 no longer provides polygons")
    expected_count = fetch(PARKS + "/query", {"where": "1=1", "returnCountOnly": "true", "f": "json"})["count"]
    parks = arcgis(PARKS, "OBJECTID,GLOBALID,FEATURE_NAME,FEATURE_CLASS,USE_DESIGNATION,PUBLIC_ACCESS,FACILITY_URL,COUNTY,MUNICIPALITY,LAST_UPDATE")
    repaired = 0
    def polygons(geometry):
        if geometry.geom_type == "Polygon":
            return [geometry]
        return [part for child in getattr(geometry, "geoms", []) for part in polygons(child)]
    for feature in parks["features"]:
        geometry = shape(feature["geometry"])
        if not geometry.is_valid:
            repaired += 1
            geometry = union_all(polygons(make_valid(geometry)))
        geometry = geometry.simplify(0.0001, preserve_topology=True)
        if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError("Park geometry cannot be safely rendered")
        feature["geometry"] = mapping(geometry)
        p = feature["properties"]
        feature["id"] = p["GLOBALID"] or str(p["OBJECTID"])
        feature["properties"] = {"id": feature["id"], "name": p["FEATURE_NAME"] or "Unnamed open space", **{k: p[k] for k in ("FEATURE_CLASS", "USE_DESIGNATION", "PUBLIC_ACCESS", "FACILITY_URL", "LAST_UPDATE")}, "county": p["COUNTY"], "township": p["MUNICIPALITY"]}
    parks["features"].sort(key=lambda f: f["id"])
    if not parks["features"] or len(parks["features"]) != expected_count or len({f["id"] for f in parks["features"]}) != expected_count:
        raise ValueError("Park count or unique identifiers do not match the service")
    if not all(f["geometry"] and f["geometry"]["type"] in {"Polygon", "MultiPolygon"} for f in parks["features"]):
        raise ValueError("Invalid park geometry")
    if fetch(PARKS + "/query", {"where": "1=1", "returnCountOnly": "true", "f": "json"})["count"] != expected_count:
        raise ValueError("Source changed during refresh; retry")
    files = {}
    args.output.mkdir(parents=True, exist_ok=True)
    for name, collection in [("counties.geojson", counties), ("parks.geojson", parks)]:
        content = json.dumps(collection, separators=(",", ":"), ensure_ascii=False).encode()
        (args.output / name).write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        prefix = "nj-counties-acs2023" if name.startswith("counties") else "njdep-open-space-67"
        files[name] = {"sha256": digest, "version_id": f"{prefix}-v2-{digest[:16]}", "features": len(collection["features"])}
    manifest = {
        "manifest_version": 2,
        "pipeline_version": "nj-web-snapshot-v2",
        "geometry_processing": {"parks": {"repair": "Shapely make_valid; retain polygonal components", "repaired_features": repaired, "simplify_degrees": 0.0001, "preserve_topology": True}},
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
        "sources": {"counties": COUNTIES, "demographics": ACS, "parks": PARKS},
        "demographics_vintage": "2019–2023 ACS 5-year estimates",
        "parks_vintage": "NJDEP administered Open Space (State Owned) Generalized; pinned service snapshot",
        "coverage": {
            "counties": "All 21 New Jersey counties; ACS 2019–2023 five-year estimates, not current-year estimates.",
            "parks": "NJDEP-administered state-owned open space only. Excludes a comprehensive inventory of municipal, county, federal and private parks. USE_DESIGNATION and PUBLIC_ACCESS are source attributes; use facility links for restrictions and current operating information.",
        },
        "parks_source": {"layer_id": 67, "name": metadata["name"], "feature_count": expected_count, "geometry": "Polygon/MultiPolygon", "latest_feature_update": max((f["properties"]["LAST_UPDATE"] or 0 for f in parks["features"]), default=0), "missing_feature_class": sum(not f["properties"]["FEATURE_CLASS"] for f in parks["features"]), "missing_public_access": sum(not f["properties"]["PUBLIC_ACCESS"] for f in parks["features"]), "missing_facility_url": sum(not f["properties"]["FACILITY_URL"] for f in parks["features"])},
        "refresh_policy": "Stage, compare counts/coverage/categories/checksums, review geometries, test, then explicitly promote and commit all three files together. Restart API. Version IDs change with content; imports never substitute a different snapshot.",
        "notes": [
            "County geometry simplified to 0.0005 degrees for web display; not a survey product.",
            "Density divides ACS population by NJOGIS county SQ_MILES (boundary area, not Census land area).",
            "Income is median household income in 2023 inflation-adjusted dollars; estimates include 90% margins of error.",
            "NJDEP layer 67 generalized open-space polygons simplified to 0.0001 degrees for web display; not tax parcels or survey boundaries. Missing FEATURE_CLASS is displayed as Unspecified, not inferred from use.",
            "ACS negative margin-of-error sentinel values are preserved; they are not numeric error bounds.",
        ],
    }
    add_points(args.output, manifest)
    existing = json.loads((DEST / "manifest.json").read_text(encoding="utf-8")) if (DEST / "manifest.json").exists() else {}
    if "tracts.geojson" in existing.get("files", {}):
        shutil.copyfile(DEST / "tracts.geojson", args.output / "tracts.geojson")
        manifest["files"]["tracts.geojson"] = existing["files"]["tracts.geojson"]
        manifest["sources"]["tracts"] = existing["sources"]["tracts"]
        manifest["coverage"]["tracts"] = existing["coverage"]["tracts"]
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(files, indent=2))


if __name__ == "__main__":
    main()
