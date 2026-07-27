"""Contract tests: GateResult invariant, SemanticContext authority boundary,
RenderPlan provenance enforcement (Blueprint §2.1, Manual §8.2)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from autocarto.contracts import (
    AreaOfInterest,
    AuthorityViolation,
    FieldSchema,
    GateResult,
    GateSuiteResult,
    MapProposal,
    Prescription,
    ProvenancedValue,
    RenderPlan,
    SemanticContext,
    adapt_gate2,
    adapt_gate3b,
)
from autocarto.execution.gates.gate2_classification import ClassificationDiagnosticEngine
from autocarto.execution.gates.gate3b_bivariate_correlation import BivariateCorrelationGate


# ── GateResult invariant ──────────────────────────────────────────────────────

def test_reject_without_prescription_raises():
    with pytest.raises(ValueError, match="requires a Prescription"):
        GateResult(gate_id="G1", decision="REJECT")


def test_reject_with_prescription_ok():
    res = GateResult(
        gate_id="G1", decision="REJECT",
        prescription=Prescription(method="x", instruction="y"),
    )
    assert res.passed is False


def test_warn_and_pass_do_not_require_prescription():
    assert GateResult(gate_id="G1", decision="WARN").passed is True
    assert GateResult(gate_id="G1", decision="PASS").passed is True


# ── Adapters ──────────────────────────────────────────────────────────────────

def test_adapt_gate2_rejection_carries_prescription():
    engine = ClassificationDiagnosticEngine(random_state=0)
    values = np.random.default_rng(3).lognormal(10, 1.2, 200)
    result = engine.evaluate(values, proposed_method="jenks")
    gr = adapt_gate2(result)
    assert gr.gate_id == "G2"
    assert gr.decision == "REJECT"
    assert gr.prescription is not None


def test_gate_suite_result_consolidates_mandate():
    engine = ClassificationDiagnosticEngine(random_state=0)
    values = np.random.default_rng(3).lognormal(10, 1.2, 200)
    gr2 = adapt_gate2(engine.evaluate(values, proposed_method="jenks"))
    suite = GateSuiteResult(results=[gr2, GateResult(gate_id="G1", decision="PASS")])
    assert suite.decision == "REJECT"
    assert len(suite.consolidated_mandate()) == 1


# ── SemanticContext authority boundary (invariant #1) ────────────────────────

def _valid_context() -> SemanticContext:
    return SemanticContext(
        dataset_schemas=[FieldSchema(name="x", dtype="float64", role="density")],
        aoi=AreaOfInterest(id="aoi-1", bbox_4326=(-85.0, 33.0, -84.0, 34.0), feature_count=10),
    )


def test_valid_semantic_context_constructs():
    ctx = _valid_context()
    assert len(ctx.prompt_hash()) == 16


def test_ndarray_in_diagnoses_rejected():
    with pytest.raises(AuthorityViolation):
        SemanticContext(
            dataset_schemas=[FieldSchema(name="x", dtype="float64")],
            aoi=AreaOfInterest(id="x", bbox_4326=(0, 0, 1, 1), feature_count=1),
            diagnoses=[np.array([1.0, 2.0])],
        )


def test_dataframe_nested_in_prescription_params_rejected():
    with pytest.raises(AuthorityViolation):
        SemanticContext(
            dataset_schemas=[FieldSchema(name="x", dtype="float64")],
            aoi=AreaOfInterest(id="x", bbox_4326=(0, 0, 1, 1), feature_count=1),
            prescriptions=[Prescription(method="m", instruction="i",
                                        params={"sneaky": pd.DataFrame({"a": [1, 2]})})],
        )


def test_series_directly_as_aoi_rejected():
    class _FakeAOI:
        pass
    with pytest.raises(AuthorityViolation):
        SemanticContext(
            dataset_schemas=[FieldSchema(name="x", dtype="float64")],
            aoi=pd.Series([1, 2, 3]),  # type: ignore[arg-type]
        )


# ── RenderPlan provenance (invariant #2) ──────────────────────────────────────

def _valid_render_plan() -> RenderPlan:
    return RenderPlan(
        breaks=ProvenancedValue([1.0, 2.0, 3.0], "GATE_PRESCRIBED", "G2"),
        projection=ProvenancedValue(5070, "GATE_PRESCRIBED", "G4"),
        palette=ProvenancedValue(["#fff", "#000"], "TEMPLATE_DEFAULT"),
        template_id=ProvenancedValue("choropleth_v1", "TEMPLATE_DEFAULT"),
    )


def test_valid_render_plan_passes_validate():
    _valid_render_plan().validate()  # no raise


@pytest.mark.parametrize("field_name", ["breaks", "projection", "palette", "template_id"])
def test_free_llm_provenance_on_any_field_rejected(field_name):
    plan = _valid_render_plan()
    setattr(plan, field_name, ProvenancedValue("anything", "FREE_LLM"))
    with pytest.raises(AuthorityViolation, match="FREE_LLM"):
        plan.validate()


def test_map_proposal_round_trips_to_dict():
    prop = MapProposal(map_type="bivariate", variables=["a", "b"], iteration=2)
    d = prop.to_dict()
    assert d["map_type"] == "bivariate"
    assert d["iteration"] == 2
