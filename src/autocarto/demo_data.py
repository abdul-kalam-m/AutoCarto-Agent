"""Offline demo dataset for `autocarto run` — real Atlanta tract geometry,
synthetic SAR variables (Manual §11 P2 acceptance: "zero network").

Uses the pinned TIGER snapshot (`data/atlanta_tracts_fulton_dekalb.geojson`,
Manual TD-7) rather than a live Census API call, and the exact SAR
generation parameters already verified in `scripts/gen_results_panel.py`
(seeds 1001/1002/1003, rho 0.72/0.35/0.35) so this CLI path reproduces the
same statistical structure as the poster's own results panel — real
geometry, known-ground-truth synthetic variables, fully offline.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SNAPSHOT_PATH = REPO_ROOT / "data" / "atlanta_tracts_fulton_dekalb.geojson"


def _sar_draw(W: np.ndarray, rho: float, seed: int) -> np.ndarray:
    from scipy.linalg import solve
    rng = np.random.default_rng(seed)
    A = np.eye(W.shape[0]) - rho * W
    eps = rng.standard_normal(W.shape[0])
    return solve(A, eps)


def load_atlanta_dataset():
    """Build a `Dataset` (autocarto.orchestrator.Dataset) from the pinned
    Atlanta tract snapshot with SAR-generated canopy-loss / asthma-rate
    variables. Requires the optional `geo` extra (geopandas, libpysal).
    """
    try:
        import geopandas as gpd
        import libpysal
    except ImportError as exc:
        raise RuntimeError(
            "autocarto run's built-in demo dataset requires the 'geo' "
            "extra: pip install -e '.[geo]' (geopandas, libpysal)."
        ) from exc

    from autocarto.orchestrator import Dataset

    if not SNAPSHOT_PATH.exists():
        raise RuntimeError(
            f"Pinned Atlanta snapshot not found at {SNAPSHOT_PATH}. "
            f"Run scripts/snapshot_tiger.py (network required) once, or "
            f"pass your own Dataset to Orchestrator.run() directly."
        )

    gdf = gpd.read_file(SNAPSHOT_PATH).to_crs(epsg=5070)

    w = libpysal.weights.Queen.from_dataframe(gdf, silence_warnings=True, use_index=True)
    if w.islands:
        keep = [i for i in range(len(gdf)) if gdf.index[i] not in w.islands]
        gdf = gdf.iloc[keep].reset_index(drop=True)
        w = libpysal.weights.Queen.from_dataframe(gdf, silence_warnings=True, use_index=True)
    w.transform = "r"
    W = w.full()[0]

    z_common = _sar_draw(W, rho=0.72, seed=1001)
    z_x = 0.78 * z_common + 0.22 * _sar_draw(W, rho=0.35, seed=1002)
    tree_canopy = np.clip(np.exp(z_x * 0.90) * 7.5, 0.5, 95.0)
    z_y = 0.75 * z_common + 0.25 * _sar_draw(W, rho=0.35, seed=1003)
    asthma_rate = np.clip(np.exp(z_y * 0.85) * 18.0, 1.0, 250.0)

    return Dataset(
        id="atlanta-fulton-dekalb",
        gdf=gdf,
        variables={"tree_canopy_loss": tree_canopy, "asthma_rate": asthma_rate},
        variable_roles={"tree_canopy_loss": "density", "asthma_rate": "rate"},
        weights=W,
        description=f"{len(gdf)} census tracts, Fulton + DeKalb Counties, GA (TIGER)",
        citation="Geometry: Census TIGER (pinned snapshot). Variables: synthetic SAR (known ground truth).",
    )
