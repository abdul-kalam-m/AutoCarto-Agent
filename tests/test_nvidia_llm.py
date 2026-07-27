"""NvidiaLLM tests — offline logic + a network-gated live integration test.

The offline tests (no key, no network) cover the parts that must be correct
regardless of what the model returns: JSON extraction from messy output,
hard validation of the model's intent against the actual schema, the
heuristic fallback, and the deterministic mandate-transcription path (which
never calls the API). The live test actually hits NVIDIA's endpoint and is
skipped automatically when NVIDIA_API_KEY is absent — network- and
cost-gated, like the real-Qdrant integration tests.
"""

from __future__ import annotations

import os

import pytest

from autocarto.contracts import AreaOfInterest, FieldSchema, Prescription, SemanticContext
from autocarto.env import get_key
from autocarto.semantic.nvidia_llm import NvidiaLLM, _extract_json

DUMMY = "dummy-key-not-used-offline"


def _ctx(prescriptions=None):
    return SemanticContext(
        dataset_schemas=[
            FieldSchema(name="median_household_income", dtype="float64", role="count", unit="USD"),
            FieldSchema(name="asthma_prevalence", dtype="float64", role="rate", unit="percent"),
        ],
        aoi=AreaOfInterest(id="atl", bbox_4326=(-84.9, 33.4, -84.0, 34.1),
                           feature_count=519, description="Atlanta tracts"),
        prescriptions=prescriptions or [],
    )


# ── _extract_json: model output is messy in practice ────────────────────────

def test_extract_json_from_fenced_block():
    assert _extract_json('```json\n{"map_type": "bivariate"}\n```') == {"map_type": "bivariate"}


def test_extract_json_from_prose_wrapped():
    out = _extract_json('Sure! {"map_type": "choropleth", "variables": ["x"]} hope that helps')
    assert out == {"map_type": "choropleth", "variables": ["x"]}


def test_extract_json_nested_braces():
    out = _extract_json('{"a": {"b": 1}, "c": [2, 3]}')
    assert out == {"a": {"b": 1}, "c": [2, 3]}


def test_extract_json_raises_on_no_object():
    with pytest.raises(ValueError):
        _extract_json("no json here at all")


# ── _validate_intent: the model must never inject bad map types or vars ─────

def test_validate_intent_accepts_clean_bivariate():
    llm = NvidiaLLM(api_key=DUMMY)
    out = llm._validate_intent(
        {"map_type": "bivariate",
         "variables": ["median_household_income", "asthma_prevalence"],
         "map_purpose": "area_comparison"},
        ["median_household_income", "asthma_prevalence"],
    )
    assert out["map_type"] == "bivariate"
    assert out["variables"] == ["median_household_income", "asthma_prevalence"]


def test_validate_intent_drops_invented_variable_names():
    llm = NvidiaLLM(api_key=DUMMY)
    out = llm._validate_intent(
        {"map_type": "choropleth", "variables": ["totally_made_up_variable"]},
        ["median_household_income", "asthma_prevalence"],
    )
    # invented name dropped -> falls back to real schema variables
    assert out["variables"]
    assert all(v in ["median_household_income", "asthma_prevalence"] for v in out["variables"])


def test_validate_intent_case_insensitive_variable_match():
    llm = NvidiaLLM(api_key=DUMMY)
    out = llm._validate_intent(
        {"map_type": "choropleth", "variables": ["MEDIAN_HOUSEHOLD_INCOME"]},
        ["median_household_income", "asthma_prevalence"],
    )
    assert out["variables"] == ["median_household_income"]


def test_validate_intent_rejects_invalid_map_type():
    llm = NvidiaLLM(api_key=DUMMY)
    out = llm._validate_intent(
        {"map_type": "3d_hologram", "variables": ["median_household_income", "asthma_prevalence"]},
        ["median_household_income", "asthma_prevalence"],
    )
    assert out["map_type"] in {"choropleth", "bivariate", "proportional_symbol"}


def test_validate_intent_bivariate_needs_two_vars_else_downgrades():
    llm = NvidiaLLM(api_key=DUMMY)
    out = llm._validate_intent(
        {"map_type": "bivariate", "variables": ["median_household_income"]},
        ["median_household_income", "asthma_prevalence"],
    )
    assert out["map_type"] == "choropleth"  # can't be bivariate with one variable
    assert out["variables"] == ["median_household_income"]


def test_validate_intent_invalid_purpose_defaults():
    llm = NvidiaLLM(api_key=DUMMY)
    out = llm._validate_intent(
        {"map_type": "choropleth", "variables": ["asthma_prevalence"], "map_purpose": "nonsense"},
        ["median_household_income", "asthma_prevalence"],
    )
    assert out["map_purpose"] == "area_comparison"


# ── Mandate transcription: no API call, deterministic ───────────────────────

def test_mandate_iteration_transcribes_without_network():
    """A context WITH prescriptions must never hit the network — it applies
    the mandate deterministically (the code-assembler role)."""
    llm = NvidiaLLM(api_key=DUMMY)  # dummy key: if this called the API it would fail
    ctx = _ctx(prescriptions=[Prescription(
        method="log_transform_then_jenks", instruction="...",
        params={"breaks": [0.5, 3.0, 6.0, 12.0, 73.0]},
    )])
    proposal, record = llm.propose(ctx, "map income")
    assert proposal.classification_method == "log_transform_then_jenks"
    assert proposal.classification_breaks == [0.5, 3.0, 6.0, 12.0, 73.0]
    assert proposal.iteration == 1
    assert record.provider == "nvidia"


def test_call_record_carries_model_and_prompt_hash():
    llm = NvidiaLLM(api_key=DUMMY)
    ctx = _ctx(prescriptions=[Prescription(method="quantile", instruction="x", params={})])
    _proposal, record = llm.propose(ctx, "map income")
    assert record.model == NvidiaLLM.DEFAULT_MODEL
    assert record.prompt_hash == ctx.prompt_hash()
    assert record.temperature == 0.0


# ── Live integration (network + cost + slowness gated) ──────────────────────
# Requires BOTH a key AND an explicit opt-in env var. The double gate is
# deliberate: the app having NVIDIA_API_KEY in .env must NOT drag every
# `pytest tests/` run through a real ~30-140s (cold-start) API call. Run it
# on demand:  AUTOCARTO_LIVE_LLM_TESTS=1 pytest tests/test_nvidia_llm.py

_HAS_KEY = get_key("NVIDIA_API_KEY", required=False) is not None
_LIVE_OPTED_IN = os.environ.get("AUTOCARTO_LIVE_LLM_TESTS") == "1"


@pytest.mark.skipif(
    not (_HAS_KEY and _LIVE_OPTED_IN),
    reason="live LLM test — set AUTOCARTO_LIVE_LLM_TESTS=1 (and NVIDIA_API_KEY) to run",
)
def test_live_intent_parse_distinguishes_bivariate_from_univariate():
    llm = NvidiaLLM()
    bivar, _ = llm.propose(_ctx(), "Show how income relates to asthma prevalence in Atlanta")
    assert bivar.map_type == "bivariate"
    assert set(bivar.variables) == {"median_household_income", "asthma_prevalence"}

    univar, _ = llm.propose(_ctx(), "Map only median household income by tract")
    assert univar.map_type == "choropleth"
    assert univar.variables == ["median_household_income"]
