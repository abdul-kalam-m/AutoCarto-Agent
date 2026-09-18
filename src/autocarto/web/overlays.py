"""Allowlisted NJ reference layers, fetched only for an explicit small extent.

Live reference data is not an input to the snapshot-based analysis engine.
Results over the feature/byte limit are refused, never silently truncated.
"""
import hashlib
import json
from datetime import datetime, timezone
from functools import lru_cache
import httpx
from pydantic import BaseModel, ConfigDict
from autocarto.offline import is_offline

DEP = "https://mapsdep.nj.gov/arcgis/rest/services/Features/"
SOURCES = {
    "parcels": {"name": "MOD-IV parcels", "url": "https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/Parcels_Composite_NJ_WM/FeatureServer/0", "color": "#7854a1", "geometry": "polygon", "fields": ["PAMS_PIN", "PROP_CLASS", "MUN_NAME"], "note": "NJOGIS parcel/MOD-IV composite. Tax records and geometries may not match completely; not a boundary survey."},
    "roads": {"name": "NJ road centerlines", "url": "https://maps.nj.gov/arcgis/rest/services/Framework/Transportation/MapServer/14", "color": "#414141", "geometry": "line", "fields": ["PRIMENAME", "LST_PNAME", "ROADCLASS"], "note": "NJOGIS NG9-1-1 road centerlines. No routing or travel-time model."},
    "infrastructure": {"name": "Power plants", "url": DEP + "Utilities/MapServer/20", "color": "#955300", "geometry": "point", "fields": ["NAME", "PLANT_NAME", "FACILITY_NAME"], "note": "NJDEP public power-generation facility locations; not all infrastructure."},
    "water": {"name": "Waterbodies (NHD 2015)", "url": DEP + "Hydrography/MapServer/33", "color": "#087ea4", "geometry": "polygon", "fields": ["GNIS_NAME", "FTYPE", "FCODE"], "note": "NJDEP NHD 2015 waterbody service. Service vintage is historical."},
    "flood": {"name": "Flood hazard areas (NFHL)", "url": DEP + "Hydrography/MapServer/43", "color": "#974397", "geometry": "polygon", "fields": ["FLD_ZONE", "ZONE_SUBTY", "SFHA_TF"], "note": "FEMA NFHL served by NJDEP. Reference only; consult the effective FEMA map for regulatory decisions."},
}
LIMIT = 2000


class OverlayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bounds: tuple[float, float, float, float]


def catalog():
    return [{"id": key, **{k: v for k, v in source.items() if k != "fields"}} for key, source in SOURCES.items()]


def _get(url, params):
    # Hard byte bound before JSON decoding, fixed host/path and no redirects.
    with httpx.stream("GET", url, params=params, timeout=30, follow_redirects=False) as response:
        response.raise_for_status()
        raw = bytearray()
        for chunk in response.iter_bytes():
            raw.extend(chunk)
            if len(raw) > 12 * 1024 * 1024:
                raise ValueError("Reference layer exceeds 12 MiB; zoom in and reload.")
    result = json.loads(raw)
    if "error" in result:
        raise ValueError("The official reference service could not complete this query. Try a smaller extent or retry later.")
    return result


@lru_cache(maxsize=5)
def metadata(key):
    return _get(SOURCES[key]["url"], {"f": "json"})


def load(key, bounds):
    if is_offline():
        raise ValueError("Live reference layers are unavailable in offline mode.")
    if key not in SOURCES:
        raise ValueError("Unknown reference dataset")
    west, south, east, north = bounds
    if not (-75.7 <= west < east <= -73.8 and 38.8 <= south < north <= 41.5) or (east - west) * (north - south) > .04:
        raise ValueError("Zoom into a smaller NJ extent (at most 0.04 square degrees), then load this view.")
    source = SOURCES[key]
    meta = metadata(key)
    fields = {f["name"] for f in meta["fields"]}
    oid = next((f["name"] for f in meta["fields"] if f["type"] == "esriFieldTypeOID"), None)
    if not oid:
        raise ValueError("Reference service has no stable object identifier; review its contract.")
    params = {"where": "1=1", "geometry": ",".join(str(x) for x in bounds), "geometryType": "esriGeometryEnvelope", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects"}
    count = _get(source["url"] + "/query", {**params, "returnCountOnly": "true", "f": "json"})["count"]
    if count > LIMIT:
        raise ValueError(f"This view contains {count:,} features (limit {LIMIT:,}). Zoom in; no partial layer was loaded.")
    features = []
    while len(features) < count:
        result = _get(source["url"] + "/query", {**params, "outFields": ",".join([oid] + [f for f in source["fields"] if f in fields]), "outSR": 4326, "f": "geojson", "orderByFields": oid, "resultOffset": len(features), "resultRecordCount": min(500, count - len(features))})
        page = result.get("features", [])
        if not page:
            raise ValueError("Reference service returned incomplete data; no partial layer was loaded.")
        features.extend(page)
        if len(json.dumps(features).encode()) > 12 * 1024 * 1024:
            raise ValueError("Reference layer exceeds 12 MiB; zoom in and reload.")
        if len(features) > LIMIT:
            raise ValueError("Reference service changed during loading; retry this extent.")
    identifiers = [f["properties"].get(oid, f.get("id")) for f in features]
    if len(features) != count or len(set(identifiers)) != count or None in identifiers:
        raise ValueError("Reference coverage/identifiers changed while loading; retry.")
    collection = {"type": "FeatureCollection", "features": features}
    return {"data": collection, "provenance": {"dataset": key, "source": source["url"], "bounds": bounds, "retrieved_at": datetime.now(timezone.utc).isoformat(), "count": count,
            "sha256": hashlib.sha256(json.dumps(collection, sort_keys=True).encode()).hexdigest(), "analysis_eligible": False,
            "coverage": "Complete service query for this bounding box at retrieval, not a statewide snapshot. Reloads may differ.", "note": source["note"]}}
