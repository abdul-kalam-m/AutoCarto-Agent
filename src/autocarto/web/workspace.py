"""Validate saved state, bind exact snapshots, and recompute imported traces."""
from copy import deepcopy
import json

from autocarto.traces import differences, validate_document
from .engine import MapRequest, park_plan, plan, read_data


def dataset_versions(version=2):
    files = read_data("manifest")["files"]
    names = ("counties", "parks", "park_points") if version >= 3 else ("counties", "parks")
    if version >= 5:
        names += ("tracts",)
    return {name: {key: files[name + ".geojson"][key] for key in ("version_id", "sha256")} for name in names}


def web_trace(settings):
    # Normalize NumPy scalar subclasses to JSON numbers and detach the record
    # from cached engine objects before returning user-owned state.
    return json.loads(json.dumps({"kind": "web-map-trace", "version": 1, "plan": plan(MapRequest(**settings)), "parks": park_plan()}, allow_nan=False))


def import_workspace(document):
    validate_document(document)
    if document["kind"] != "workspace":
        raise ValueError("This file is a validation trace, not a restorable workspace")
    if document["datasets"] != dataset_versions(document["version"]):
        raise ValueError("Dataset version mismatch. Restore the exact pinned snapshots named in the workspace; no data was substituted.")
    county_id = document["view"]["selected_county"]
    known_counties = {f["id"] for f in read_data("counties")["features"]}
    if not set(document.get("county_filter", [])) <= known_counties:
        raise ValueError("County filter contains a county outside the pinned snapshot")
    if county_id and county_id not in {f["id"] for f in read_data("counties")["features"]}:
        raise ValueError("Selected county does not exist in this snapshot")
    trace = web_trace(document["settings"])
    if differences(document["trace"], trace):
        raise ValueError("Saved trace differs from recomputed validation. The file may be modified or use a different engine version; the workspace was not applied.")
    if document["version"] >= 5:
        from .spatial import ProximityRequest, proximity
        state = document["phase2"]
        if state["distance_m"] is None:
            if state["result_id"] is not None:
                raise ValueError("A proximity result requires its buffer distance")
        else:
            result = proximity(ProximityRequest(distance_m=state["distance_m"], counties=document["county_filter"]))
            if not result["applied"] or state["result_id"] != result["record"]["result_id"]:
                raise ValueError("Saved proximity verdict/result differs from recomputed analysis")
    restored = deepcopy(document)
    restored["trace"] = trace
    return restored
