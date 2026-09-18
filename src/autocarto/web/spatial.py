"""Deterministic park-point proximity, with separate operation gate verdicts."""
from functools import lru_cache
import hashlib
import json
import geopandas as gpd
from pydantic import BaseModel, ConfigDict, Field
from autocarto.execution.gates.gate1_crs import CRSIntegrityGate
from autocarto.execution.gates.gate4_projection_distortion import ProjectionDistortionGate
from autocarto.execution.gates.gate6_completeness import CompletenessGate, RenderManifest
from autocarto.execution.gates.gate7_buffer import BufferGate
from autocarto.execution.gates.gate8_spatial_join import SpatialJoinGate
from .engine import read_data

BOUNDS = (-75.58, 38.9, -73.89, 41.36)


class ProximityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    distance_m: float = Field(allow_inf_nan=False)
    purpose: str = Field(default="exploratory_proximity", max_length=100)
    source: str = Field(default="park_points", max_length=50)
    counties: list[str] = Field(default_factory=list, max_length=21)


@lru_cache(maxsize=3)
def frame(dataset, epsg):
    return gpd.GeoDataFrame.from_features(read_data(dataset)["features"], crs=4326).set_index("id", drop=False).to_crs(epsg)


def proximity(request):
    # Never silently substitute polygon boundaries for the requested point input.
    if request.source != "park_points":
        from autocarto.contracts import GateResult, Prescription
        return {"applied": False, "trace": [GateResult("G7", "REJECT", {"source": request.source}, Prescription("use_park_points", "Select the pinned historical NJ park point snapshot.")).to_dict()]}
    known = {f["id"] for f in read_data("counties")["features"]}
    if not set(request.counties) <= known or len(set(request.counties)) != len(request.counties):
        raise ValueError("Select unique NJ county IDs")
    return _proximity(request.distance_m, request.purpose, tuple(sorted(request.counties)))


@lru_cache(maxsize=2)
def _proximity(distance, purpose, counties):
    points = frame("park_points", 32111)
    tracts = frame("tracts", 32111)
    if counties:
        tracts = tracts[tracts["county_id"].isin(counties)]
    # All NJ points are retained, including points across a selected county's
    # boundary. County filters restrict target tracts, never potential buffers.
    gate = BufferGate().evaluate(points, distance, purpose)
    trace = [gate.to_dict()]
    if not gate.passed:
        return {"applied": False, "trace": trace}
    buffers = points.copy()
    buffers.geometry = points.geometry.buffer(distance, resolution=32)
    g1 = CRSIntegrityGate().evaluate(tracts, "choropleth", "count", join_gdf=buffers)
    g4 = ProjectionDistortionGate().evaluate(32111, BOUNDS, "distance")
    join = SpatialJoinGate().evaluate(tracts, buffers)
    trace.extend(g.to_dict() for g in (g1, g4, join))
    if not all(g.passed for g in (g1, g4, join)):
        return {"applied": False, "trace": trace}
    indices = buffers.sindex.query(tracts.geometry, predicate="intersects")[0]
    matched = sorted(set(tracts.iloc[indices].index))
    files = read_data("manifest")["files"]
    record = {"kind": "spatial-operation-trace", "operation": "park_point_proximity", "version": 1, "source": "park_points", "distance_m": distance,
              "purpose": purpose, "counties": list(counties), "crs": "EPSG:32111", "predicate": "intersects",
              "datasets": {name: {k: files[name + ".geojson"][k] for k in ("version_id", "sha256")} for name in ("park_points", "tracts")},
              "matched_tract_ids": matched, "tracts_considered": len(tracts), "trace": trace}
    record["result_id"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    from autocarto.traces import validate_document
    validate_document(record)
    # A buffer per point keeps identity/provenance; overlaps are intentional.
    display = buffers[["id", "name", "geometry"]].to_crs(4326)
    return {"applied": True, "record": record, "trace": trace, "buffers": json.loads(display.to_json(drop_id=True))}


@lru_cache(maxsize=6)
def map_geometry_checks(dataset, metric="density"):
    # Audit the actual Web Mercator renderer. Do not pretend an equal-area
    # analysis CRS certifies this different display projection.
    geometry = frame(dataset, 3857)
    role = {"density": "density", "population": "count", "income": "ordinal"}[metric]
    return [CRSIntegrityGate().evaluate(geometry, "choropleth", role).to_dict(),
            ProjectionDistortionGate().evaluate(3857, BOUNDS, "area_comparison").to_dict()]


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=200)
    legend_present: bool = False
    scale_bar_present: bool = False
    data_citation: str | None = Field(default=None, max_length=500)
    crs_note: str | None = Field(default=None, max_length=200)
    classification_note: str | None = Field(default=None, max_length=200)


def render_check(request):
    return CompletenessGate().evaluate(RenderManifest(**request.model_dump()), "choropleth").to_dict()
