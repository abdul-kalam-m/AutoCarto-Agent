"""Deterministic validation gates.

Implemented: Gate 2 (classification diagnostics, prescriptive rejection)
and Gate 3b (bivariate spatial cross-correlation). Gates 1/3a/4/5/6 are
specified in Fable Review/03_V2_PRODUCTION_BLUEPRINT.md §3.
"""

from autocarto.execution.gates.gate2_classification import (
    ClassificationDiagnosticEngine,
    DiagnosticResult,
    DistributionProfile,
    characterize_distribution,
)
from autocarto.execution.gates.gate3b_bivariate_correlation import (
    BivariateCorrelationGate,
    BivariateCorrelationResult,
)

__all__ = [
    "ClassificationDiagnosticEngine",
    "DiagnosticResult",
    "DistributionProfile",
    "characterize_distribution",
    "BivariateCorrelationGate",
    "BivariateCorrelationResult",
]
