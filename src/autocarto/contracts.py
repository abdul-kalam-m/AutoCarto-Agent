"""Unified contracts for the gate suite and orchestrator.

Every gate (G1..G6) returns a `GateResult`. This is the structural backbone
specified in ``Fable Review/01_OPERATING_MANUAL.md`` §8.2 and
``Fable Review/03_V2_PRODUCTION_BLUEPRINT.md`` §2.1.

Two invariants are enforced here as code, not convention:

1. A `GateResult` with ``decision == "REJECT"`` MUST carry a `Prescription`.
   A rejection without a remedy is a contract violation (Manual §6.1-1: the
   prescriptive-rejection pattern is the project's core contribution), so it
   is a raised `ValueError` at construction time, not a runtime possibility.
2. `SemanticContext` (the only object permitted into an LLM prompt)
   structurally cannot hold a NumPy array or pandas Series/DataFrame
   anywhere in its payload — the authority boundary becomes a type error,
   not intent (Blueprint §2.1).

Gate 2 and Gate 3b predate this contract and are NOT modified — they are
tested and their traces are golden (byte-identical regression fixtures).
`adapt_gate2` / `adapt_gate3b` are pure, lossless translations of their
existing result objects into `GateResult`, per Manual §8.2 ("do the
adapter, don't rewrite the gates").
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Dict, List, Literal, Optional, TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from autocarto.execution.gates.gate2_classification import DiagnosticResult
    from autocarto.execution.gates.gate3b_bivariate_correlation import BivariateCorrelationResult

GateDecision = Literal["PASS", "WARN", "REJECT"]
GateId = Literal["G1", "G2", "G3a", "G3b", "G4", "G5", "G6"]

# Canonical gate execution order (Blueprint §3.6): geometry/projection
# validity gates the statistics; classification depends on the (possibly
# reprojected) data; color/completeness gate the render.
GATE_ORDER: tuple[GateId, ...] = ("G1", "G4", "G3a", "G3b", "G2", "G5", "G6")


class AuthorityViolation(Exception):
    """Raised when raw data attempts to cross the Tier-1/Tier-2 boundary.

    The LLM tier may only ever see schemas, diagnoses, and prescriptions.
    Any attempt to construct a `SemanticContext` carrying an ndarray,
    pandas Series/DataFrame, or GeoDataFrame raises this — the "zero
    statistical authority leakage" claim becomes falsifiable at runtime.
    """


# ════════════════════════════════════════════════════════════════════════════
# Gate result contract
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class Prescription:
    """A mandated remedy attached to a REJECT (or annotated WARN) decision.

    Fields mirror what Gate 2 already returns informally
    (``prescribed_method`` / ``prescribed_breaks`` / ``instruction`` /
    ``code_snippet``), so the existing gates fold into this losslessly.
    """
    method: str
    instruction: str
    params: Dict[str, Any] = field(default_factory=dict)
    code_snippet: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "instruction": self.instruction,
            "params": self.params,
            "code_snippet": self.code_snippet,
        }


@dataclass
class GateResult:
    """Unified result every gate (G1..G6) returns to the orchestrator."""
    gate_id: GateId
    decision: GateDecision
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    prescription: Optional[Prescription] = None
    instruction: Optional[str] = None

    def __post_init__(self) -> None:
        if self.decision == "REJECT" and self.prescription is None:
            raise ValueError(
                f"{self.gate_id}: REJECT requires a Prescription — a "
                f"rejection with no remedy violates the prescriptive-"
                f"rejection contract (Manual §6.1-1)."
            )

    @property
    def passed(self) -> bool:
        """True for PASS and WARN — only REJECT blocks execution."""
        return self.decision != "REJECT"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.gate_id,
            "decision": self.decision,
            "passed": self.passed,
            "diagnostics": self.diagnostics,
            "prescription": self.prescription.to_dict() if self.prescription else None,
            "instruction": self.instruction,
        }


@dataclass
class GateSuiteResult:
    """Aggregated outcome of running the full gate suite against one proposal."""
    results: List[GateResult]

    @property
    def decision(self) -> GateDecision:
        if any(r.decision == "REJECT" for r in self.results):
            return "REJECT"
        if any(r.decision == "WARN" for r in self.results):
            return "WARN"
        return "PASS"

    @property
    def rejections(self) -> List[GateResult]:
        return [r for r in self.results if r.decision == "REJECT"]

    def consolidated_mandate(self) -> List[Prescription]:
        """All prescriptions from REJECTed gates, for a single re-prompt.

        Blueprint §3.6: collect every rejection's prescription and send one
        consolidated mandate back to the LLM rather than round-tripping
        gate-by-gate — fewer iterations, lower latency and cost.
        """
        return [r.prescription for r in self.rejections if r.prescription is not None]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "gates": [r.to_dict() for r in self.results],
            "rejection_count": len(self.rejections),
        }


# ── Adapters: fold the two pre-existing, tested gates into GateResult ───────

def adapt_gate2(result: "DiagnosticResult") -> GateResult:
    """Translate a Gate 2 ``DiagnosticResult`` into a ``GateResult``."""
    prescription = None
    if not result.passed:
        prescription = Prescription(
            method=result.prescribed_method or "quantile",
            instruction=result.instruction or "",
            params={
                "breaks": result.prescribed_breaks,
                "diagnosis": result.diagnosis,
                "gvf": result.gvf,
            },
            code_snippet=result.code_snippet,
        )
    return GateResult(
        gate_id="G2",
        decision="PASS" if result.passed else "REJECT",
        diagnostics={"diagnosis": result.diagnosis, "gvf": round(result.gvf, 4)},
        prescription=prescription,
        instruction=result.instruction,
    )


def adapt_gate3b(result: "BivariateCorrelationResult") -> GateResult:
    """Translate a Gate 3b ``BivariateCorrelationResult`` into a ``GateResult``."""
    decision: GateDecision = "PASS" if result.decision == "APPROVE" else result.decision  # type: ignore[assignment]

    prescription = None
    if decision == "REJECT":
        prescription = Prescription(
            method="side_by_side_univariate",
            instruction=result.instruction or "",
            params={
                "bivariate_morans_i": result.bivariate_morans_i,
                "spearman_rho": result.spearman_rho,
            },
        )
    return GateResult(
        gate_id="G3b",
        decision=decision,
        diagnostics={
            "bivariate_morans_i": round(result.bivariate_morans_i, 4),
            "bivariate_morans_p": round(result.bivariate_morans_p, 4),
            "spearman_rho": round(result.spearman_rho, 4),
            "spearman_p": round(result.spearman_p, 4),
        },
        prescription=prescription,
        instruction=result.instruction,
    )


# ════════════════════════════════════════════════════════════════════════════
# Provenance — invariant #2: no numeric render constant of free-LLM origin
# ════════════════════════════════════════════════════════════════════════════

Provenance = Literal["GATE_PRESCRIBED", "TEMPLATE_DEFAULT", "FREE_LLM"]


@dataclass
class ProvenancedValue:
    """A render constant tagged with where it came from.

    `RenderPlan` (below) refuses to validate if any field's provenance is
    ``FREE_LLM`` — the LLM may choose *which* prescribed value or template
    default to use, but may never invent a number that reaches the sandbox.
    """
    value: Any
    provenance: Provenance
    source_gate: Optional[GateId] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "provenance": self.provenance,
            "source_gate": self.source_gate,
        }


# ════════════════════════════════════════════════════════════════════════════
# P2 — Orchestrator contracts: MapProposal, SemanticContext, RenderPlan
# (Blueprint §2.1, §4, §5)
# ════════════════════════════════════════════════════════════════════════════

MapType = Literal["choropleth", "bivariate", "proportional_symbol"]
VariableRole = Literal["density", "count", "rate", "ordinal"]
MapPurpose = Literal["area_comparison", "shape", "distance"]


@dataclass
class FieldSchema:
    """Name/dtype/unit metadata for a variable — never its values.

    This is the *only* form a variable may take inside a `SemanticContext`.
    """
    name: str
    dtype: str
    unit: Optional[str] = None
    description: Optional[str] = None
    role: Optional[VariableRole] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "dtype": self.dtype, "unit": self.unit,
                "description": self.description, "role": self.role}


@dataclass
class AreaOfInterest:
    """Geometry identity + bbox — not the vertex arrays the LLM would need
    to reason spatially. Real geometry lives in Tier 2 only."""
    id: str
    bbox_4326: tuple  # (minx, miny, maxx, maxy) — a bbox is a 4-tuple of
                       # floats, not raw geometry; it does not encode the
                       # AOI's actual shape and cannot substitute for the
                       # real GeoDataFrame used downstream in Tier 2.
    feature_count: int
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "bbox_4326": list(self.bbox_4326),
                "feature_count": self.feature_count, "description": self.description}


@dataclass
class MapProposal:
    """What Tier 1 (the LLM) produces: a declarative description of a map,
    never the data or the render code itself (Blueprint §4 Propose step).

    Every field here is either a category choice (map_type, template_id),
    a variable *name* (never values), or a numeric constant that Tier 2
    will independently validate — nothing here is trusted until the gate
    suite runs.
    """
    map_type: MapType
    variables: List[str]
    variable_roles: Dict[str, VariableRole] = field(default_factory=dict)
    classification_method: Optional[str] = None
    classification_breaks: Optional[List[float]] = None
    projection_epsg: Optional[int] = None
    palette: Optional[List[str]] = None
    diverging_palette: bool = False
    template_id: Optional[str] = None
    map_purpose: MapPurpose = "area_comparison"
    iteration: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "map_type": self.map_type,
            "variables": self.variables,
            "variable_roles": self.variable_roles,
            "classification_method": self.classification_method,
            "classification_breaks": self.classification_breaks,
            "projection_epsg": self.projection_epsg,
            "palette": self.palette,
            "diverging_palette": self.diverging_palette,
            "template_id": self.template_id,
            "map_purpose": self.map_purpose,
            "iteration": self.iteration,
        }


_RAW_DATA_TYPES = (np.ndarray, pd.Series, pd.DataFrame)


def _assert_no_raw_data(value: Any, path: str = "root") -> None:
    """Recursively walk a value; raise AuthorityViolation on any raw-data type.

    Walks dict/list/tuple containers and dataclass fields. This is invariant
    #1 (Blueprint §2.1) made structural: it is called from every
    `SemanticContext` constructor path, so building one with an ndarray
    buried anywhere in its payload fails immediately, not silently.
    """
    if isinstance(value, _RAW_DATA_TYPES):
        raise AuthorityViolation(
            f"raw data ({type(value).__name__}) may not enter an LLM "
            f"context — found at {path}. The authority boundary requires "
            f"schemas/diagnoses/prescriptions only (Blueprint §2.1)."
        )
    # geopandas is optional; check by class name to avoid a hard dependency.
    if type(value).__name__ in ("GeoDataFrame", "GeoSeries"):
        raise AuthorityViolation(
            f"raw geometry ({type(value).__name__}) may not enter an LLM "
            f"context — found at {path}."
        )
    if isinstance(value, dict):
        for k, v in value.items():
            _assert_no_raw_data(v, f"{path}.{k}")
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _assert_no_raw_data(v, f"{path}[{i}]")
    elif is_dataclass(value) and not isinstance(value, type):
        for f in fields(value):
            _assert_no_raw_data(getattr(value, f.name), f"{path}.{f.name}")


@dataclass(frozen=True)
class SemanticContext:
    """The ONLY object permitted to be serialized into an LLM prompt.

    Contains dataset schemas, the AOI's identity/bbox, gate diagnoses, and
    prescriptions — structurally never raw data. Construction itself
    enforces this: `__post_init__` walks every field and raises
    `AuthorityViolation` if it finds an ndarray/Series/DataFrame/
    GeoDataFrame anywhere in the payload, at any nesting depth.
    """
    dataset_schemas: List[FieldSchema]
    aoi: AreaOfInterest
    diagnoses: List[str] = field(default_factory=list)
    prescriptions: List[Prescription] = field(default_factory=list)

    def __post_init__(self) -> None:
        _assert_no_raw_data(self.dataset_schemas, "dataset_schemas")
        _assert_no_raw_data(self.aoi, "aoi")
        _assert_no_raw_data(self.diagnoses, "diagnoses")
        _assert_no_raw_data(self.prescriptions, "prescriptions")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_schemas": [s.to_dict() for s in self.dataset_schemas],
            "aoi": self.aoi.to_dict(),
            "diagnoses": self.diagnoses,
            "prescriptions": [p.to_dict() for p in self.prescriptions],
        }

    def prompt_hash(self) -> str:
        """Stable hash of the serialized context, for trace provenance."""
        payload = json.dumps(self.to_dict(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]


@dataclass
class RenderPlan:
    """Everything needed to render, with every numeric constant tagged by
    provenance. `validate()` refuses a plan containing any FREE_LLM value
    — invariant #2: no render constant of free-LLM origin ever reaches the
    sandbox (Blueprint §2.1).
    """
    breaks: ProvenancedValue
    projection: ProvenancedValue
    palette: ProvenancedValue
    template_id: ProvenancedValue

    def validate(self) -> None:
        for f in fields(self):
            pv: ProvenancedValue = getattr(self, f.name)
            if pv.provenance == "FREE_LLM":
                raise AuthorityViolation(
                    f"RenderPlan.{f.name} has FREE_LLM provenance — a "
                    f"render constant not backed by a gate prescription or "
                    f"template default cannot be executed."
                )

    def to_dict(self) -> Dict[str, Any]:
        return {f.name: getattr(self, f.name).to_dict() for f in fields(self)}
