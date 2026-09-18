"""G8: complete-input, unique-identifier intersection selection contract."""
from autocarto.contracts import GateResult, Prescription


class SpatialJoinGate:
    def evaluate(self, left, right, predicate="intersects", complete=True):
        problems = []
        if predicate != "intersects":
            problems.append("Use the reviewed intersects predicate (boundary touches count).")
        if not complete:
            problems.append("Use complete snapshots; a truncated viewport response cannot be analysed.")
        if left.crs is None or right.crs is None or left.crs != right.crs or not left.crs.is_projected:
            problems.append("Reproject both inputs into the same projected CRS.")
        for name, frame in (("tracts", left), ("buffers", right)):
            if frame.empty or not frame.index.is_unique or frame.index.hasnans:
                problems.append(f"Provide nonempty {name} with unique, non-null identifiers.")
            if not frame.geometry.is_valid.all() or frame.geometry.is_empty.any() or not frame.geom_type.isin(["Polygon", "MultiPolygon"]).all():
                problems.append(f"Repair or reject invalid {name} polygon geometry before joining.")
        diagnostics = {"predicate": predicate, "left_count": len(left), "right_count": len(right),
                       "complete": complete, "output": "unique intersecting tract IDs", "boundary_touches_included": True,
                       "population_aggregation": "none", "multiplicity": "deduplicate tracts across all park buffers"}
        if problems:
            return GateResult("G8", "REJECT", diagnostics, Prescription("review_join_inputs", " ".join(problems)))
        return GateResult("G8", "PASS", diagnostics, instruction="Select unique intersecting tracts; do not interpret whole-tract population as people within buffers.")
