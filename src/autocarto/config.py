"""Centralized, versioned gate thresholds — Manual §6.2-4 / TD-8.

Every numeric threshold used anywhere in the gate suite lives here, each
with a ``rationale`` explaining where the number comes from. This does not
yet include a calibration study (Blueprint §9 "threshold sensitivity" /
research task R-1 remains open) — these are the values already shipped in
Gate 2 and Gate 3b, now given a single, citable home instead of being
scattered as bare class constants, plus the new gates' thresholds specified
in Blueprint §3.

Gate 2 and Gate 3b keep their own class-level constants (they are tested,
and duplicating the values here would create two sources of truth); this
module re-exports them alongside the five new gates' thresholds so a single
import gives the complete, current threshold set. If you change a Gate
2/3b constant, change it at the source and update the rationale here.

Usage:
    from autocarto.config import THRESHOLDS
    if abs(morans_i) < THRESHOLDS.gate3a.reject_below_abs_i: ...
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Gate1Thresholds:
    """CRS integrity — Blueprint §3.1."""
    require_equal_area_for_density: bool = True
    rationale: str = (
        "Density/rate choropleths (e.g. population per sq km) computed in a "
        "geographic CRS (lat/lon degrees) silently misrepresent area because "
        "a degree of longitude is not constant length. This is a correctness "
        "requirement, not a calibrated statistic — no sweep applies."
    )


@dataclass(frozen=True)
class Gate2Thresholds:
    """Classification diagnostic — values live on ClassificationDiagnosticEngine.

    Re-exported here (not redefined) so config.py is a complete index.
    """
    gvf_threshold: float = 0.6
    zero_inflation_threshold: float = 0.40
    outlier_threshold: float = 0.10
    discrete_threshold: int = 10
    max_iterations: int = 3
    rationale: str = (
        "GVF 0.6 is the standard cartographic-classification acceptability "
        "floor (Jenks/Coulson tradition: <0.6 poor fit, 0.6-0.8 acceptable, "
        ">0.8 excellent). Zero-inflation 40% and outlier 10% are the values "
        "shipped since the original review pass; no formal sensitivity sweep "
        "has been run yet (Blueprint §9 R-1, still open)."
    )


@dataclass(frozen=True)
class Gate3aThresholds:
    """Univariate spatial structure (Moran's I) — Blueprint §3.2."""
    reject_below_abs_i: float = 0.10
    permutations: int = 999
    significance_alpha: float = 0.05
    rationale: str = (
        "|I| < 0.10 is the conventional 'negligible spatial autocorrelation' "
        "cutoff in the spatial-statistics literature (Moran's I ranges "
        "roughly [-1, 1] for typical contiguity weights; values this close "
        "to the -1/(N-1) expectation under CSR are indistinguishable from "
        "noise for cartographic purposes). 999 permutations is the "
        "PySAL/esda default for inference-grade Moran's I."
    )


@dataclass(frozen=True)
class Gate3bThresholds:
    """Bivariate cross-correlation — values live on BivariateCorrelationGate.

    Re-exported here (not redefined) so config.py is a complete index.
    """
    approve_i_threshold: float = 0.15
    approve_rho_threshold: float = 0.20
    warn_i_threshold: float = 0.08
    warn_rho_threshold: float = 0.10
    default_permutations: int = 199
    rationale: str = (
        "Thresholds are roughly half the univariate Gate 3a cutoff, "
        "reflecting that bivariate cross-correlation is a noisier, "
        "compound statistic. 199 permutations balances p-value resolution "
        "(minimum achievable p = 1/200 = 0.005) against runtime for "
        "interactive use. No formal sensitivity sweep has been run "
        "(Blueprint §9 R-1, still open)."
    )


@dataclass(frozen=True)
class Gate4Thresholds:
    """Projection distortion (Tissot) — Blueprint §3.3."""
    max_areal_exaggeration: float = 0.20
    graticule_resolution: int = 12
    rationale: str = (
        "20% maximum areal exaggeration is the threshold specified in the "
        "abstract (C4) for area-comparison maps. A 12x12 graticule over the "
        "AOI balances distortion-sampling fidelity against the cost of a "
        "pyproj factor computation at each node; adequate for tract/county/ "
        "state-scale AOIs where distortion varies smoothly. Not yet swept "
        "(Blueprint §9 R-1)."
    )


@dataclass(frozen=True)
class Gate5Thresholds:
    """Color-vision accessibility — Blueprint §3.4."""
    min_delta_e_adjacent_classes: float = 10.0
    min_wcag_contrast_ratio: float = 4.5
    rationale: str = (
        "Delta-E (CIEDE2000) of 10 between perceptually-adjacent classes "
        "under each CVD simulation is a conservative 'clearly distinguishable' "
        "threshold (a JND is ~1-2 dE; cartographic classes should be well "
        "above just-noticeable to survive print/screen degradation). WCAG "
        "2.1 4.5:1 is the published Level AA contrast requirement for "
        "normal-size text, applied here to legend/label text against its "
        "background."
    )


@dataclass(frozen=True)
class Gate6Thresholds:
    """Map completeness — Blueprint §3.5."""
    required_elements_choropleth: tuple = (
        "title", "legend", "scale_or_graticule", "citation",
        "crs_note", "classification_note",
    )
    required_elements_bivariate: tuple = (
        "title", "bivariate_legend", "scale_or_graticule", "citation",
        "crs_note", "classification_note", "correlation_statistic",
    )
    required_elements_proportional_symbol: tuple = (
        "title", "legend", "scale_or_graticule", "citation", "crs_note",
    )
    rationale: str = (
        "Required-element sets follow standard cartographic-completeness "
        "checklists (Slocum et al., Thematic Cartography and Geovisualization); "
        "bivariate maps additionally require the correlation statistic that "
        "justified Gate 3b's approval, so the map is self-documenting about "
        "why a bivariate encoding was used."
    )


@dataclass(frozen=True)
class ThresholdRegistry:
    gate1: Gate1Thresholds = Gate1Thresholds()
    gate2: Gate2Thresholds = Gate2Thresholds()
    gate3a: Gate3aThresholds = Gate3aThresholds()
    gate3b: Gate3bThresholds = Gate3bThresholds()
    gate4: Gate4Thresholds = Gate4Thresholds()
    gate5: Gate5Thresholds = Gate5Thresholds()
    gate6: Gate6Thresholds = Gate6Thresholds()


THRESHOLDS = ThresholdRegistry()


# ── Equal-area CRS lookup — Gate 1 / Gate 4 prescriptions (Blueprint §3.1) ──
# EPSG code per AOI scale. Not exhaustive; covers the scales this project's
# demos and benchmark actually exercise.
EQUAL_AREA_CRS_BY_SCALE = {
    "conus": 5070,      # NAD83 / Conus Albers
    "state": None,       # resolved per-state via STATE_PLANE_ALBERS below
    "global": 8857,      # Equal Earth Greenwich
}

# A sampling of commonly-used state-level equal-area CRS (NAD83 state-grid
# Albers where published; falls back to CONUS Albers 5070 if a state is not
# listed — 5070 remains equal-area, just not state-optimized).
STATE_EQUAL_AREA_CRS = {
    "GA": 5070,   # Georgia falls back to CONUS Albers (no dedicated state Albers in common use)
    "CA": 3310,   # NAD83 / California Albers
    "TX": 3083,   # NAD83 / Texas Centric Albers Equal Area
    "NY": 5070,
}
