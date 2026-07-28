"""Real-data Atlanta dataset — Blueprint §6.1/§6.3 P4-T1.

Parallel to demo_data.py, but with real ACS income and real CDC PLACES
asthma prevalence in place of SAR-synthetic variables — the "real
variables alongside the SAR synthetic (keep both)" utility case study
Blueprint §6.3 calls for. Synthetic stays the *validity* fixture (known
ground truth); this is the *utility* demonstration (does the pipeline
produce something sensible on data nobody engineered to have a particular
statistical structure).

Tracts missing either real variable (the same ~2 non-residential "Tract
9800" entries in each county that lack a BRFSS estimate, plus any ACS
Census-sentinel tract) are dropped before building spatial weights — real
demographic/health data has real coverage gaps; imputing them would
manufacture structure the gates would then be validating against data
that was never actually measured.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TIGER_SNAPSHOT = REPO_ROOT / "data" / "atlanta_tracts_fulton_dekalb.geojson"
ACS_SNAPSHOT = REPO_ROOT / "data" / "acs_median_household_income_2022.csv"
CDC_SNAPSHOT = REPO_ROOT / "data" / "cdc_places_asthma_2023.csv"


def load_real_atlanta_dataset(*, variables: Optional[list] = None):
    """Build a `Dataset` from real TIGER geometry + real ACS + real CDC
    PLACES data — no synthetic variables. Requires the optional `geo`
    extra (geopandas, libpysal).

    Args:
        variables: which real variables to include; defaults to both
            ["median_household_income", "asthma_prevalence"]. Pass a
            single-element list for a univariate (choropleth) case.
    """
    try:
        import geopandas as gpd
        import libpysal
    except ImportError as exc:
        raise RuntimeError(
            "load_real_atlanta_dataset requires the 'geo' extra: "
            "pip install -e '.[geo]' (geopandas, libpysal)."
        ) from exc

    from autocarto.data_fabric.connectors.acs import load_acs_snapshot
    from autocarto.data_fabric.connectors.cdc_places import load_cdc_places_snapshot
    from autocarto.orchestrator import Dataset

    for path in (TIGER_SNAPSHOT, ACS_SNAPSHOT, CDC_SNAPSHOT):
        if not path.exists():
            raise RuntimeError(
                f"Missing real-data snapshot: {path}. See data/MANIFEST.md "
                f"for how each one is (re)generated."
            )

    variables = variables or ["median_household_income", "asthma_prevalence"]

    gdf = gpd.read_file(TIGER_SNAPSHOT)
    income_by_geoid = load_acs_snapshot(ACS_SNAPSHOT)
    asthma_by_geoid = load_cdc_places_snapshot(CDC_SNAPSHOT)

    gdf["median_household_income"] = gdf["GEOID"].map(income_by_geoid)
    gdf["asthma_prevalence"] = gdf["GEOID"].map(asthma_by_geoid)

    # Drop tracts missing any requested real variable -- real coverage
    # gaps (non-residential tracts), not imputed.
    gdf = gdf.dropna(subset=variables).reset_index(drop=True)

    gdf = gdf.to_crs(epsg=5070)

    w = libpysal.weights.Queen.from_dataframe(gdf, silence_warnings=True, use_index=True)
    if w.islands:
        keep = [i for i in range(len(gdf)) if gdf.index[i] not in w.islands]
        gdf = gdf.iloc[keep].reset_index(drop=True)
        w = libpysal.weights.Queen.from_dataframe(gdf, silence_warnings=True, use_index=True)
    w.transform = "r"
    W = w.full()[0]

    variable_arrays = {v: np.asarray(gdf[v].values, dtype=float) for v in variables}
    variable_roles = {
        "median_household_income": "count",  # not an area-normalized statistic
        "asthma_prevalence": "rate",          # a per-capita rate (%), conservatively CRS-gated
    }

    return Dataset(
        id="atlanta-fulton-dekalb-real",
        gdf=gdf,
        variables=variable_arrays,
        variable_roles={k: v for k, v in variable_roles.items() if k in variables},
        weights=W,
        description=(
            f"{len(gdf)} census tracts (real, non-imputed), Fulton + DeKalb "
            f"Counties, GA — real ACS + CDC PLACES data, no SAR synthetic"
        ),
        # Split by source: `citation` alone (geometry) applies to every map;
        # `citation_by_variable` only gets appended for a variable actually
        # in a given proposal, so a map of income alone never claims CDC
        # asthma data it never touched, and vice versa -- see
        # Orchestrator._resolve_citation.
        citation="Geometry: Census TIGER (pinned snapshot).",
        citation_by_variable={
            "median_household_income": "Income: Census ACS 5-Year 2022, table B19013.",
            "asthma_prevalence": "Asthma: CDC PLACES 2023, measure CASTHMA.",
        },
        variable_units={k: v for k, v in {
            "median_household_income": "USD",
            "asthma_prevalence": "percent",
        }.items() if k in variables},
    )
