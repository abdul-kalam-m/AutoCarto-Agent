"""Shared builder for the Atlanta case study (real TIGER geometry, seeded SAR
variables). Used by the results panel and the ungated-vs-gated figure so the
data-generating process is defined once.

Requires the [geo] extra (geopandas, libpysal). Not imported by the package
core, which must stay dependency-light.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

import numpy as np
from scipy.linalg import solve as sp_solve
from threadpoolctl import threadpool_limits

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SNAPSHOT = os.path.join(REPO_ROOT, "data", "atlanta_tracts_fulton_dekalb.geojson")

TIGER_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "Tracts_Blocks/MapServer/4/query"
    "?where=STATE%3D%2713%27+AND+COUNTY+IN+%28%27121%27%2C%27089%27%29"
    "&outFields=GEOID%2CNAME%2CSTATE%2CCOUNTY%2CTRACT"
    "&f=geojson&outSR=4326&resultRecordCount=2000"
)


@dataclass
class AtlantaCase:
    gdf: "object"          # GeoDataFrame in EPSG:26967 (GA state plane)
    W_rs: np.ndarray       # row-standardised queen-contiguity weights (n x n)
    tree_canopy: np.ndarray
    asthma_rate: np.ndarray
    n: int


def _sar_draw(W: np.ndarray, rho: float, seed: int) -> np.ndarray:
    """One SAR(rho) realisation: y = (I - rho*W)^-1 * eps.

    Runs the solve with BLAS pinned to 1 thread: GitHub Actions'
    ubuntu-latest runner segfaults inside scipy.linalg.solve otherwise —
    OpenBLAS's thread-count autodetection misbehaves on that runner's
    constrained CPU topology (see https://github.com/OpenMathLib/OpenBLAS/issues/2993).
    Scoped to just this call (not a process-wide env var) since forcing
    single-threaded BLAS globally in CI was observed to stall the rest of
    the suite instead.
    """
    rng = np.random.default_rng(seed)
    A = np.eye(W.shape[0]) - rho * W
    with threadpool_limits(limits=1):
        return sp_solve(A, rng.standard_normal(W.shape[0]))


def build_atlanta_case(live: bool = False) -> AtlantaCase:
    """Load geometry, build queen weights, draw the two seeded SAR variables.

    Reproduces the exact construction used for the poster results panel
    (seeds 1001/1002/1003), so both figures share identical inputs.
    """
    import geopandas as gpd
    import libpysal

    if live:
        req = urllib.request.Request(TIGER_URL, headers={"User-Agent": "CartoLLM/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    else:
        if not os.path.exists(SNAPSHOT):
            raise SystemExit(
                "Snapshot missing. Run `python scripts/snapshot_tiger.py` once "
                "(network required) or pass live=True."
            )
        with open(SNAPSHOT, "r", encoding="utf-8") as fh:
            payload = json.load(fh)

    gdf = gpd.GeoDataFrame.from_features(payload["features"], crs="EPSG:4326").to_crs(epsg=26967)

    W_q = libpysal.weights.Queen.from_dataframe(gdf, use_index=False, silence_warnings=True)
    if W_q.islands:
        keep = [i for i in range(len(gdf)) if gdf.index[i] not in W_q.islands]
        gdf = gdf.iloc[keep].reset_index(drop=True)
        W_q = libpysal.weights.Queen.from_dataframe(gdf, use_index=False, silence_warnings=True)
    W_q.transform = "r"
    W_rs = W_q.full()[0]
    assert np.allclose(W_rs.sum(axis=1), 1.0, atol=1e-6)

    # Shared latent spatial factor drives the cross-correlation (seeds fixed).
    z_common = _sar_draw(W_rs, rho=0.72, seed=1001)
    z_x = 0.78 * z_common + 0.22 * _sar_draw(W_rs, rho=0.35, seed=1002)
    tree_canopy = np.clip(np.exp(z_x * 0.90) * 7.5, 0.5, 95.0)
    z_y = 0.75 * z_common + 0.25 * _sar_draw(W_rs, rho=0.35, seed=1003)
    asthma_rate = np.clip(np.exp(z_y * 0.85) * 18.0, 1.0, 250.0)

    return AtlantaCase(gdf=gdf, W_rs=W_rs, tree_canopy=tree_canopy,
                       asthma_rate=asthma_rate, n=len(gdf))
