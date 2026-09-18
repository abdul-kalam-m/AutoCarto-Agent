"""G7: bounded, explicit, exploratory point-buffer contract.

Distance is a user-selected scenario, not a claim of access. The 10 km ceiling
is a service scope limit, not a scientifically recommended catchment radius.
"""
import math
import pyproj
from autocarto.contracts import GateResult, Prescription


class BufferGate:
    def evaluate(self, points, distance_m, purpose, source_complete=True):
        problems = []
        if type(distance_m) not in (int, float) or not math.isfinite(distance_m) or not 1 <= distance_m <= 10000:
            problems.append("Choose an explicit distance from 1 to 10,000 metres.")
        if purpose != "exploratory_proximity":
            problems.append("Only exploratory geometric proximity is supported; walking access is not inferred.")
        if not source_complete or points.empty or not points.index.is_unique:
            problems.append("Use complete, nonempty inputs with unique point identifiers.")
        if points.crs is None or points.crs.to_epsg() != 32111:
            problems.append("Project NJ points to EPSG:32111 (NAD83 / New Jersey, metres).")
        if not points.geometry.is_valid.all() or points.geometry.is_empty.any() or not points.geom_type.eq("Point").all():
            problems.append("Supply valid, nonempty Point geometry; park polygons are not supported.")
        error = None
        if not problems:
            ll = points.to_crs(4326)
            if not all(-75.7 <= p.x <= -73.8 and 38.8 <= p.y <= 41.5 for p in ll.geometry):
                problems.append("The buffer contract covers NJ point locations only.")
            projection = pyproj.Proj(32111)
            errors = []
            # Sample a 0.15-degree envelope around every center (larger than
            # the permitted 10 km radius in NJ) in both linear directions.
            for point in ll.geometry:
                for dx in (-.15, 0, .15):
                    for dy in (-.15, 0, .15):
                        factors = projection.get_factors(point.x + dx, point.y + dy)
                        errors.extend((abs(factors.meridional_scale - 1), abs(factors.parallel_scale - 1)))
            error = max(errors)
            if not math.isfinite(error) or error > .001:
                problems.append("Measured linear distortion exceeds 0.1%; review the distance CRS.")
        diagnostics = {"input_geometry": "Point", "input_count": len(points), "distance_m": distance_m if type(distance_m) in (int, float) and math.isfinite(distance_m) else None,
                       "purpose": purpose, "max_linear_scale_error": error, "linear_error_limit": .001,
                       "buffer_quadrant_segments": 32, "max_polygon_radial_error_fraction": 1 - math.cos(math.pi / 128)}
        if problems:
            return GateResult("G7", "REJECT", diagnostics, Prescription("review_buffer_inputs", " ".join(problems)))
        return GateResult("G7", "WARN", diagnostics, instruction="Exploratory distance scenario around historical park points. Not entrances, public access, walking distance, or residents served. Polygonal circles have up to 0.031% radial approximation error.")
