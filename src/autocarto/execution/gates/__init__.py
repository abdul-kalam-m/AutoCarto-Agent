"""Deterministic validation gates — all six now implemented.

Execution order (contracts.GATE_ORDER): G1 -> G4 -> [G3a | G3b] -> G2 -> G5 -> G6.
Geometry/projection validity gates the statistics; classification depends
on the (possibly reprojected) data; color/completeness gate the render.

G2 and G3b predate the unified GateResult contract and are adapted via
``autocarto.contracts.adapt_gate2`` / ``adapt_gate3b`` rather than rewritten
(Manual §8.2) — they remain independently importable in their original
form for callers that don't need the unified contract.
"""

from autocarto.execution.gates.gate1_crs import CRSIntegrityGate
from autocarto.execution.gates.gate2_classification import (
    ClassificationDiagnosticEngine,
    DiagnosticResult,
    DistributionProfile,
    characterize_distribution,
)
from autocarto.execution.gates.gate3a_spatial_autocorrelation import SpatialStructureGate
from autocarto.execution.gates.gate3b_bivariate_correlation import (
    BivariateCorrelationGate,
    BivariateCorrelationResult,
)
from autocarto.execution.gates.gate4_projection_distortion import ProjectionDistortionGate
from autocarto.execution.gates.gate5_color_accessibility import ColorAccessibilityGate
from autocarto.execution.gates.gate6_completeness import CompletenessGate, RenderManifest

__all__ = [
    "CRSIntegrityGate",
    "ClassificationDiagnosticEngine",
    "DiagnosticResult",
    "DistributionProfile",
    "characterize_distribution",
    "SpatialStructureGate",
    "BivariateCorrelationGate",
    "BivariateCorrelationResult",
    "ProjectionDistortionGate",
    "ColorAccessibilityGate",
    "CompletenessGate",
    "RenderManifest",
]
