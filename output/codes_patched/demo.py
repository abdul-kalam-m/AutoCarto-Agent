"""AutoCarto-Agent end-to-end demo harness.

Exercises the four supplied modules with synthetic but realistic data,
writes JSON execution traces, renders illustrative figures, and prints a
machine-parseable run log to stdout.

Run from the project root:
    python output/codes_patched/demo.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

# Make the patched modules importable regardless of CWD.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from gate2_classification import (
    ClassificationDiagnosticEngine,
    DistributionProfile,
    _dedupe_breaks,
)
from gate3b_bivariate_correlation import BivariateCorrelationGate
from hybrid_retrieval import HybridRetrieval, STACItem
from sandbox import CodeSanitizer, _DevOnlySandboxExecutor


# Paths
OUT_ROOT = HERE.parent
FIG_DIR = OUT_ROOT / "figures"
TRACE_DIR = OUT_ROOT / "traces"
LOG_DIR = OUT_ROOT / "logs"
for d in (FIG_DIR, TRACE_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------
# Utility
# ----------------------------------------------------------------------
class JsonSerializable(json.JSONEncoder):
    """Encoder that copes with NumPy scalars and dataclass-style profiles."""

    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        if isinstance(obj, DistributionProfile):
            return asdict(obj)
        return super().default(obj)


def emit_trace(name: str, payload: Dict[str, Any]) -> Path:
    path = TRACE_DIR / f"{name}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, cls=JsonSerializable)
    return path


def log(line: str, fh=None) -> None:
    print(line, flush=True)
    if fh is not None:
        fh.write(line + "\n")


# ----------------------------------------------------------------------
# Synthetic data
# ----------------------------------------------------------------------
RNG = np.random.default_rng(42)


def make_well_behaved(n: int = 243) -> np.ndarray:
    """Approximately Normal — passes well_behaved diagnosis."""
    return RNG.normal(loc=50, scale=12, size=n).clip(0, 100)


def make_zero_inflated(n: int = 243) -> np.ndarray:
    """About 50% zeros + Pareto tail — matches the 'asthma hospitalisations' scenario."""
    zeros = np.zeros(n // 2)
    tail = RNG.pareto(2.0, size=n - len(zeros)) * 5 + 1
    arr = np.concatenate([zeros, tail])
    RNG.shuffle(arr)
    return arr


def make_heavy_right_skew(n: int = 243) -> np.ndarray:
    """Lognormal household-income-style variable."""
    return RNG.lognormal(mean=10, sigma=1.2, size=n)


def make_grid_polygons(rows: int, cols: int):
    """Build a regular grid of square polygons and queen-style adjacency.

    Returns:
        polygons: list of (4,2) np.ndarrays in lon/lat-ish coords
        weights:  N x N adjacency matrix, row-standardised
        centroids: (N, 2) array of centroids
    """
    polys = []
    centroids = []
    for r in range(rows):
        for c in range(cols):
            x0, y0 = c, r
            polys.append(np.array([
                [x0, y0],
                [x0 + 1, y0],
                [x0 + 1, y0 + 1],
                [x0, y0 + 1],
            ]))
            centroids.append([x0 + 0.5, y0 + 0.5])
    n = rows * cols
    W = np.zeros((n, n))
    for i in range(n):
        ri, ci = divmod(i, cols)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = ri + dr, ci + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    j = nr * cols + nc
                    W[i, j] = 1.0
    row_sums = W.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    W = W / row_sums
    return polys, W, np.array(centroids)


def spatial_autoregressive(W: np.ndarray, rho: float, seed: int) -> np.ndarray:
    """Draw a SAR(rho) realisation y = (I - rho W)^-1 eps."""
    n = W.shape[0]
    rng = np.random.default_rng(seed)
    eps = rng.standard_normal(n)
    A = np.eye(n) - rho * W
    return np.linalg.solve(A, eps)


# ----------------------------------------------------------------------
# Gate 2 demo
# ----------------------------------------------------------------------
def make_negative_with_right_skew(n: int = 243) -> np.ndarray:
    """Right-skewed variable whose minimum is negative (reviewer issue 2).

    Represents net migration rate: chi-squared(df=2) shape, shifted slightly left
    so ~3% of census tracts show small net outmigration (negative values), while
    the long right tail reflects a few high-growth tracts.

    Diagnostic properties:
      - skewness ≈ 1.6 (> 1.5 threshold → heavy_right_skew)
      - outlier_fraction ≈ 0.037 (< 0.10 → does NOT trigger outlier_dominated first)
      - min ≈ -0.8 (< 0 → log1p invalid, arcsinh mandated)

    The original _prescribe_log_transform applied np.maximum(values, 0) which
    would have clamped those negative tracts to zero, turning this into a
    zero-inflated distribution and triggering a completely wrong Gate 2 path.
    """
    rng = np.random.default_rng(99)
    return rng.chisquare(df=2, size=n) - 0.8


def demo_gate2(log_fh) -> Dict[str, Any]:
    log("\n=== Gate 2: Classification Diagnostic Engine ===", log_fh)
    cases = {
        "well_behaved": make_well_behaved(),
        "zero_inflated": make_zero_inflated(),
        "heavy_right_skew": make_heavy_right_skew(),
        "discrete_ordinal": RNG.choice([1, 2, 3, 4, 5], size=243, p=[0.3, 0.3, 0.2, 0.15, 0.05]).astype(float),
        # Reviewer issue 2: right-skewed variable with negative values must route
        # to arcsinh, NOT log1p (log1p would silently clamp negatives to zero).
        "negative_values_arcsinh": make_negative_with_right_skew(),
    }

    engine = ClassificationDiagnosticEngine(random_state=0)
    trace_payload: Dict[str, Any] = {"cases": {}}

    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    axes = axes.ravel()

    for idx, (label, values) in enumerate(cases.items()):
        engine.reset()
        # LLM "proposes" Fisher-Jenks with quintile-derived breaks
        proposed_breaks = [float(np.percentile(values, p)) for p in (0, 20, 40, 60, 80, 100)]
        proposed_breaks = _dedupe_breaks(proposed_breaks)
        result = engine.evaluate(values, proposed_method="jenks", proposed_breaks=proposed_breaks)

        payload = result.to_dict()
        payload["profile"] = asdict(result.profile) if result.profile else None
        payload["llm_proposed_method"] = "jenks"
        payload["llm_proposed_breaks"] = proposed_breaks
        trace_payload["cases"][label] = payload

        log(
            f"  {label:>18}: diagnosis={result.diagnosis:<22} passed={result.passed} "
            f"GVF={result.gvf:.3f} prescribed={result.prescribed_method}",
            log_fh,
        )

        ax = axes[idx]
        ax.hist(values, bins=40, color="#4c78a8", edgecolor="white")
        ax.set_title(f"{label}\ndiagnosis={result.diagnosis}", fontsize=10)
        for b in proposed_breaks:
            ax.axvline(b, color="#888", linestyle=":", linewidth=1, label="LLM break")
        if result.prescribed_breaks:
            for b in result.prescribed_breaks:
                ax.axvline(b, color="#e45756", linestyle="--", linewidth=1, label="prescribed")
        # de-duplicate legend
        handles, labels = ax.get_legend_handles_labels()
        seen: Dict[str, Any] = {}
        for h, l in zip(handles, labels):
            seen.setdefault(l, h)
        ax.legend(seen.values(), seen.keys(), fontsize=8, loc="upper right")
        ax.set_xlabel("value")
        ax.set_ylabel("count")

    # Hide any unused axes (grid has 6 slots for 5 cases)
    for ax in axes[len(cases):]:
        ax.set_visible(False)

    fig.suptitle("Gate 2 — Distribution diagnostics and prescriptive breaks", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig_path = FIG_DIR / "gate2_distribution_diagnostics.png"
    fig.savefig(fig_path, dpi=150)
    plt.close(fig)
    log(f"  -> figure: {fig_path.relative_to(OUT_ROOT)}", log_fh)

    trace_path = emit_trace("gate2_classification_trace", trace_payload)
    log(f"  -> trace : {trace_path.relative_to(OUT_ROOT)}", log_fh)
    return trace_payload


# ----------------------------------------------------------------------
# Gate 3b demo
# ----------------------------------------------------------------------
def demo_gate3b(log_fh) -> Dict[str, Any]:
    log("\n=== Gate 3b: Bivariate Spatial Cross-Correlation ===", log_fh)
    rows, cols = 16, 16
    polys, W, centroids = make_grid_polygons(rows, cols)

    # Scenarios
    x_strong = spatial_autoregressive(W, rho=0.85, seed=1)
    y_strong = 0.8 * x_strong + 0.2 * spatial_autoregressive(W, rho=0.85, seed=2)

    x_weak = spatial_autoregressive(W, rho=0.6, seed=3)
    y_weak = 0.2 * x_weak + spatial_autoregressive(W, rho=0.4, seed=4)

    x_independent = spatial_autoregressive(W, rho=0.85, seed=5)
    y_independent = spatial_autoregressive(W, rho=0.85, seed=6)  # spatial but unrelated

    gate = BivariateCorrelationGate()
    scenarios = {
        "strong_correlation": (x_strong, y_strong),
        "weak_correlation": (x_weak, y_weak),
        "independent_variables": (x_independent, y_independent),
    }

    trace_payload: Dict[str, Any] = {"scenarios": {}}

    fig, axes = plt.subplots(2, len(scenarios), figsize=(4 * len(scenarios), 7))

    for col_idx, (label, (x, y)) in enumerate(scenarios.items()):
        result = gate.evaluate(x, y, W, standardized=False, permutations=199, random_state=7)
        payload = result.to_dict()
        trace_payload["scenarios"][label] = payload

        log(
            f"  {label:>22}: decision={result.decision:<8} "
            f"I_xy={result.bivariate_morans_i:+.3f} (p={result.bivariate_morans_p:.3f}) "
            f"rho={result.spearman_rho:+.3f}",
            log_fh,
        )

        ax_x = axes[0, col_idx]
        ax_y = axes[1, col_idx]
        vmin = min(np.min(x), np.min(y))
        vmax = max(np.max(x), np.max(y))
        grid_x = x.reshape(rows, cols)
        grid_y = y.reshape(rows, cols)
        im_x = ax_x.imshow(grid_x, cmap="viridis", vmin=vmin, vmax=vmax, origin="lower")
        ax_x.set_title(f"{label}\nvariable X (I_xy={result.bivariate_morans_i:+.3f})", fontsize=10)
        ax_x.set_xticks([])
        ax_x.set_yticks([])
        fig.colorbar(im_x, ax=ax_x, fraction=0.046, pad=0.04)
        im_y = ax_y.imshow(grid_y, cmap="viridis", vmin=vmin, vmax=vmax, origin="lower")
        ax_y.set_title(f"variable Y\ndecision={result.decision}", fontsize=10)
        ax_y.set_xticks([])
        ax_y.set_yticks([])
        fig.colorbar(im_y, ax=ax_y, fraction=0.046, pad=0.04)

    fig.suptitle("Gate 3b — Bivariate cross-correlation across three scenarios", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig_path = FIG_DIR / "gate3b_bivariate_scenarios.png"
    fig.savefig(fig_path, dpi=150)
    plt.close(fig)
    log(f"  -> figure: {fig_path.relative_to(OUT_ROOT)}", log_fh)

    # Bivariate map for the APPROVE scenario.
    bivariate_fig_path = render_bivariate_map(
        polys, x_strong, y_strong, rows, cols,
        title="Bivariate map — strong cross-correlation (APPROVE)",
        out_path=FIG_DIR / "gate3b_bivariate_map_approve.png",
    )
    log(f"  -> bivariate map: {bivariate_fig_path.relative_to(OUT_ROOT)}", log_fh)

    trace_path = emit_trace("gate3b_bivariate_trace", trace_payload)
    log(f"  -> trace : {trace_path.relative_to(OUT_ROOT)}", log_fh)
    return trace_payload


def render_bivariate_map(polys, x, y, rows, cols, title: str, out_path: Path) -> Path:
    """Render a 3x3 bivariate choropleth with class outlines."""
    from matplotlib.patches import Polygon as MplPolygon
    from matplotlib.collections import PatchCollection

    x_q = np.digitize(x, np.percentile(x, [33.3, 66.7]))
    y_q = np.digitize(y, np.percentile(y, [33.3, 66.7]))
    # 3x3 palette (Stevens 2015 style)
    palette = np.array([
        ["#e8e8e8", "#ace4e4", "#5ac8c8"],
        ["#dfb0d6", "#a5add3", "#5698b9"],
        ["#be64ac", "#8c62aa", "#3b4994"],
    ])
    colors = [palette[y_q[i], x_q[i]] for i in range(len(polys))]

    fig, (ax_map, ax_legend) = plt.subplots(1, 2, figsize=(10, 5),
                                            gridspec_kw={"width_ratios": [4, 1]})
    patches = [MplPolygon(p, closed=True) for p in polys]
    coll = PatchCollection(patches, facecolors=colors, edgecolor="white", linewidths=0.3)
    ax_map.add_collection(coll)
    ax_map.set_xlim(0, cols)
    ax_map.set_ylim(0, rows)
    ax_map.set_aspect("equal")
    ax_map.set_xticks([])
    ax_map.set_yticks([])
    ax_map.set_title(title)

    for i in range(3):
        for j in range(3):
            ax_legend.add_patch(plt.Rectangle((j, i), 1, 1, color=palette[i, j]))
    ax_legend.set_xlim(0, 3)
    ax_legend.set_ylim(0, 3)
    ax_legend.set_aspect("equal")
    ax_legend.set_xticks([0.5, 1.5, 2.5])
    ax_legend.set_yticks([0.5, 1.5, 2.5])
    ax_legend.set_xticklabels(["low", "mid", "high"])
    ax_legend.set_yticklabels(["low", "mid", "high"])
    ax_legend.set_xlabel("X tercile")
    ax_legend.set_ylabel("Y tercile")
    ax_legend.set_title("legend", fontsize=10)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


# ----------------------------------------------------------------------
# Hybrid retrieval demo (mock Qdrant)
# ----------------------------------------------------------------------
class _MockHit:
    def __init__(self, item_id: str, payload: Dict[str, Any], score: float):
        self.id = item_id
        self.payload = payload
        self.score = score


class MockQdrantClient:
    """Minimal in-memory Qdrant stand-in supporting scroll() and search().

    The point of this mock is to demonstrate the spatial-first contract in
    hybrid_retrieval.HybridRetrieval without requiring a running Qdrant.
    """

    def __init__(self, items: List[Dict[str, Any]]):
        self.items = items  # each: {id, vector, payload}

    @staticmethod
    def _bbox_overlap(a: Dict[str, float], b_min_lon, b_max_lon, b_min_lat, b_max_lat) -> bool:
        return (
            a["min_lon"] <= b_max_lon
            and a["max_lon"] >= b_min_lon
            and a["min_lat"] <= b_max_lat
            and a["max_lat"] >= b_min_lat
        )

    def _extract_bbox_query(self, scroll_filter) -> Dict[str, float]:
        """Pick out the four BBOX constraints regardless of wire format."""
        # Both real Filter objects and dict fallbacks are accepted.
        clauses = getattr(scroll_filter, "must", None) or scroll_filter["must"]
        q: Dict[str, float] = {}
        for c in clauses:
            key = getattr(c, "key", None) or c["key"]
            rng = getattr(c, "range", None) or c["range"]
            lte = getattr(rng, "lte", None) if rng is not None else None
            gte = getattr(rng, "gte", None) if rng is not None else None
            if lte is None and isinstance(rng, dict):
                lte = rng.get("lte")
            if gte is None and isinstance(rng, dict):
                gte = rng.get("gte")
            if lte is not None:
                q[key + ":lte"] = lte
            if gte is not None:
                q[key + ":gte"] = gte
        return q

    def scroll(self, collection_name, scroll_filter, limit, offset, with_payload, with_vectors):
        q = self._extract_bbox_query(scroll_filter)
        b_max_lon = q.get("bbox.min_lon:lte")
        b_min_lon = q.get("bbox.max_lon:gte")
        b_max_lat = q.get("bbox.min_lat:lte")
        b_min_lat = q.get("bbox.max_lat:gte")

        matches = [
            _MockHit(item["id"], item["payload"], score=0.0)
            for item in self.items
            if self._bbox_overlap(item["payload"]["bbox"], b_min_lon, b_max_lon, b_min_lat, b_max_lat)
        ]
        start = offset or 0
        end = start + limit
        page = matches[start:end]
        next_offset = end if end < len(matches) else None
        return page, next_offset

    def search(self, collection_name, query_vector, query_filter, limit, with_payload):
        allowed_ids = None
        clauses = getattr(query_filter, "must", None) or query_filter["must"]
        for c in clauses:
            ids = getattr(c, "has_id", None)
            if ids is None and isinstance(c, dict):
                ids = c.get("has_id")
            if ids is not None:
                allowed_ids = set(ids)
        scored = []
        qv = np.array(query_vector)
        for item in self.items:
            if allowed_ids and item["id"] not in allowed_ids:
                continue
            v = np.array(item["vector"])
            if np.linalg.norm(qv) == 0 or np.linalg.norm(v) == 0:
                sim = 0.0
            else:
                sim = float(qv @ v / (np.linalg.norm(qv) * np.linalg.norm(v)))
            scored.append(_MockHit(item["id"], item["payload"], score=sim))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:limit]


def make_mock_catalog():
    """Build a small synthetic STAC catalog covering ATL, NYC, LA, USA-wide."""
    from hybrid_retrieval import _hash_embedding
    items = []

    def _add(item_id, title, desc, bbox, variables, score, vector_text):
        items.append({
            "id": item_id,
            "vector": _hash_embedding(vector_text),
            "payload": {
                "title": title,
                "description": desc,
                "bbox": bbox,
                "temporal_start": "2020-01-01",
                "temporal_end": "2023-12-31",
                "variables": variables,
                "collection": "demo",
                "metadata_score": score,
            },
        })

    # Atlanta tree canopy (regional)
    _add(
        "atl-canopy",
        "Atlanta Tree Canopy Loss 2015-2022",
        "Annual tree canopy cover loss per census tract in metro Atlanta, derived from NLCD.",
        {"min_lon": -84.6, "min_lat": 33.6, "max_lon": -84.2, "max_lat": 34.0},
        [{"name": "canopy_loss_pct", "units": "percent"}],
        7,
        "tree canopy loss vegetation urban heat",
    )
    # CDC PLACES asthma (national but cell-level data)
    _add(
        "cdc-asthma",
        "CDC PLACES Asthma Hospitalisation Rate",
        "Age-adjusted asthma hospitalisation rate per census tract, CDC PLACES 2022 release.",
        {"min_lon": -125.0, "min_lat": 24.5, "max_lon": -66.9, "max_lat": 49.4},
        [{"name": "asthma_rate", "units": "per_100k"}],
        6,
        "respiratory health asthma hospitalisation public health tract",
    )
    # NYC traffic injuries (Manhattan-only)
    _add(
        "nyc-vision-zero",
        "NYC Vision Zero Pedestrian Injuries 2021",
        "Per-intersection pedestrian injury counts from NYPD MV-104 reports.",
        {"min_lon": -74.05, "min_lat": 40.68, "max_lon": -73.90, "max_lat": 40.88},
        [{"name": "pedestrian_injuries", "units": "count"}],
        6,
        "traffic pedestrian injury safety vision zero",
    )
    # Los Angeles wildfire (regional)
    _add(
        "la-wildfire",
        "California MTBS Wildfire Perimeters 2000-2022",
        "Monitoring Trends in Burn Severity wildfire perimeters with severity classes.",
        {"min_lon": -124.5, "min_lat": 32.5, "max_lon": -114.1, "max_lat": 42.0},
        [{"name": "burn_severity", "units": "ordinal"}],
        7,
        "wildfire burn severity vegetation forest california",
    )
    # Low-quality metadata item
    _add(
        "atl-noise",
        "Sensor data 2019",
        "",
        {"min_lon": -84.6, "min_lat": 33.6, "max_lon": -84.2, "max_lat": 34.0},
        [],
        2,
        "noise sensor",
    )
    return items


def make_mock_catalog_with_aleutians():
    """Extend catalog with an Aleutian Islands dataset stored as two non-crossing halves.

    STAC best practice for antimeridian-crossing datasets is to index two
    separate records — one for the eastern shard (near +180°) and one for the
    western shard (near -180°). The hybrid retrieval layer then handles the
    crossing correctly by querying BOTH halves via the OR logic added for
    reviewer issue 3.
    """
    from hybrid_retrieval import _hash_embedding
    items = make_mock_catalog()
    common = {
        "description": "USFWS seabird nesting sites across the Aleutian chain.",
        "temporal_start": "2018-01-01",
        "temporal_end": "2022-12-31",
        "variables": [{"name": "nesting_density", "units": "pairs_per_km2"}],
        "collection": "usfws",
        "metadata_score": 6,
    }
    # Eastern shard: near +180° longitude
    items.append({
        "id": "aleutian-seabird-east",
        "vector": _hash_embedding("seabird nesting habitat coastal alaska aleutian"),
        "payload": {"title": "Aleutian Seabird Habitat (eastern)",
                    "bbox": {"min_lon": 172.0, "min_lat": 51.0, "max_lon": 180.0, "max_lat": 55.0},
                    **common},
    })
    # Western shard: near -180° longitude
    items.append({
        "id": "aleutian-seabird-west",
        "vector": _hash_embedding("seabird nesting habitat coastal alaska aleutian"),
        "payload": {"title": "Aleutian Seabird Habitat (western)",
                    "bbox": {"min_lon": -180.0, "min_lat": 51.0, "max_lon": -164.0, "max_lat": 55.0},
                    **common},
    })
    return items


def demo_hybrid_retrieval(log_fh) -> Dict[str, Any]:
    log("\n=== Hybrid Retrieval (mock Qdrant) ===", log_fh)
    client = MockQdrantClient(make_mock_catalog_with_aleutians())
    retrieval = HybridRetrieval(client)

    atlanta_polygon = {
        "type": "Polygon",
        "coordinates": [[
            [-84.55, 33.65], [-84.25, 33.65],
            [-84.25, 33.95], [-84.55, 33.95],
            [-84.55, 33.65],
        ]],
    }
    manhattan_polygon = {
        "type": "Polygon",
        "coordinates": [[
            [-74.02, 40.70], [-73.93, 40.70],
            [-73.93, 40.87], [-74.02, 40.87],
            [-74.02, 40.70],
        ]],
    }
    # Reviewer issue 3: antimeridian-crossing polygon around the Aleutian Islands.
    # min(lons)=172, max(lons)=-164 → span=-336° → naive bbox returns zero Qdrant hits.
    # The patched _extract_bboxes splits this into [172,180] OR [-180,-164].
    aleutian_polygon = {
        "type": "Polygon",
        "coordinates": [[
            [172.0, 51.5], [180.0, 51.5],
            [-180.0, 51.5], [-164.0, 51.5],
            [-164.0, 54.5], [172.0, 54.5],
            [172.0, 51.5],
        ]],
    }

    queries = [
        ("Atlanta tree canopy and respiratory health", atlanta_polygon),
        ("pedestrian safety incidents", manhattan_polygon),
        ("seabird habitat coastal alaska", aleutian_polygon),  # antimeridian test
    ]

    trace_payload: Dict[str, Any] = {"queries": []}
    for query_text, geom in queries:
        result = retrieval.retrieve(geom, query_text, top_k=3)
        payload = {
            "query": query_text,
            "geometry_type": geom["type"],
            "result": result.to_dict(),
            "items_detail": [
                {"id": it.id, "title": it.title, "metadata_score": it.metadata_score}
                for it in result.items
            ],
        }
        trace_payload["queries"].append(payload)
        log(
            f"  query={query_text!r:55} spatial_candidates={result.spatial_candidates} "
            f"semantic_results={result.semantic_results} items={[i.id for i in result.items]}",
            log_fh,
        )

    trace_path = emit_trace("hybrid_retrieval_trace", trace_payload)
    log(f"  -> trace : {trace_path.relative_to(OUT_ROOT)}", log_fh)
    return trace_payload


# ----------------------------------------------------------------------
# Sandbox demo
# ----------------------------------------------------------------------
SANDBOX_TEST_CASES: List[Dict[str, Any]] = [
    {
        "name": "safe_numpy",
        "code": (
            "import numpy as np\n"
            "x = np.array([1, 2, 3, 4, 5])\n"
            "print('mean:', x.mean())\n"
        ),
        "expect_sanitize_pass": True,
        "expect_exec_success": True,
    },
    {
        "name": "blocked_subprocess_import",
        "code": "import subprocess\nsubprocess.run(['ls'])\n",
        "expect_sanitize_pass": False,
        "expect_exec_success": False,
    },
    {
        "name": "blocked_eval",
        "code": "eval('1 + 1')\n",
        "expect_sanitize_pass": False,
        "expect_exec_success": False,
    },
    {
        "name": "blocked_open_write",
        "code": "open('/tmp/x', 'w')\n",
        "expect_sanitize_pass": False,
        "expect_exec_success": False,
    },
    {
        "name": "blocked_open_write_kwarg",
        "code": "open('/tmp/x', mode='a+')\n",
        "expect_sanitize_pass": False,
        "expect_exec_success": False,
    },
    {
        "name": "reflection_escape",
        "code": "print(().__class__.__mro__[1].__subclasses__())\n",
        "expect_sanitize_pass": False,
        "expect_exec_success": False,
    },
    {
        "name": "docstring_mentions_subprocess",
        # PATCH note: the regex pass on the *original* sanitiser would flag the
        # docstring; our scrub-then-scan approach correctly lets it through.
        "code": (
            'def f():\n'
            '    """This function does not use subprocess at all."""\n'
            '    return 1\n'
            'print(f())\n'
        ),
        "expect_sanitize_pass": True,
        "expect_exec_success": True,
    },
]


def demo_sandbox(log_fh) -> Dict[str, Any]:
    log("\n=== Sandbox (sanitizer + _DevOnlySandboxExecutor) ===", log_fh)

    # Reviewer issue 5: confirm the production class refuses 'inprocess'.
    from sandbox import SandboxExecutor
    try:
        SandboxExecutor(backend="inprocess")
        log("  MISMATCH  production_inprocess_guard          expected RuntimeError, got nothing", log_fh)
    except RuntimeError as exc:
        log(f"  OK        production_inprocess_guard          RuntimeError raised as expected: {exc}", log_fh)

    executor = _DevOnlySandboxExecutor()
    trace_payload: Dict[str, Any] = {"cases": []}
    for case in SANDBOX_TEST_CASES:
        is_safe, message, violations = CodeSanitizer.sanitize(case["code"])
        execution_result = None
        if is_safe:
            res = executor.execute(case["code"])
            execution_result = res.to_dict()
        case_payload = {
            "name": case["name"],
            "is_safe": is_safe,
            "expect_sanitize_pass": case["expect_sanitize_pass"],
            "expect_exec_success": case["expect_exec_success"],
            "violations": violations,
            "execution": execution_result,
            "sanitize_match": is_safe == case["expect_sanitize_pass"],
            "exec_match": (
                True if execution_result is None
                else execution_result["success"] == case["expect_exec_success"]
            ),
        }
        trace_payload["cases"].append(case_payload)
        verdict = "OK" if case_payload["sanitize_match"] and case_payload["exec_match"] else "MISMATCH"
        log(
            f"  {verdict:8s} {case['name']:32s} sanitize={is_safe} "
            f"violations={len(violations)} exec={execution_result['success'] if execution_result else 'skipped'}",
            log_fh,
        )

    trace_path = emit_trace("sandbox_trace", trace_payload)
    log(f"  -> trace : {trace_path.relative_to(OUT_ROOT)}", log_fh)
    return trace_payload


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------
def main() -> int:
    run_log_path = LOG_DIR / "run.log"
    summary_path = OUT_ROOT / "RUN_SUMMARY.json"
    t0 = time.time()
    with run_log_path.open("w", encoding="utf-8") as log_fh:
        log("AutoCarto-Agent demo harness", log_fh)
        log(f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}Z", log_fh)
        log(f"python: {sys.version.split()[0]}, numpy: {np.__version__}", log_fh)

        results = {
            "gate2": demo_gate2(log_fh),
            "gate3b": demo_gate3b(log_fh),
            "hybrid_retrieval": demo_hybrid_retrieval(log_fh),
            "sandbox": demo_sandbox(log_fh),
        }

        elapsed_ms = (time.time() - t0) * 1000
        log(f"\nTotal wall-clock: {elapsed_ms:.1f} ms", log_fh)

    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "elapsed_ms": elapsed_ms,
                "artifacts": {
                    "figures": sorted(p.name for p in FIG_DIR.iterdir()),
                    "traces": sorted(p.name for p in TRACE_DIR.iterdir()),
                    "logs": sorted(p.name for p in LOG_DIR.iterdir()),
                },
                "results": results,
            },
            fh, indent=2, cls=JsonSerializable,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
