"""MockLLM behavioral tests — Blueprint §5 / Manual P2 acceptance criteria."""

from __future__ import annotations

from autocarto.contracts import AreaOfInterest, FieldSchema, Prescription, SemanticContext
from autocarto.semantic.llm_client import MockLLM


def _context(prescriptions=None) -> SemanticContext:
    return SemanticContext(
        dataset_schemas=[FieldSchema(name="tree_canopy_loss", dtype="float64", role="density")],
        aoi=AreaOfInterest(id="atl", bbox_4326=(-84.9, 33.4, -84.0, 34.1), feature_count=530),
        prescriptions=prescriptions or [],
    )


def test_fresh_proposal_has_no_computed_breaks():
    """A first-pass proposal cannot invent break values it never saw the data for."""
    llm = MockLLM()
    proposal, record = llm.propose(_context(), "Map tree canopy loss")
    assert proposal.classification_method == "jenks"
    assert proposal.classification_breaks is None
    assert proposal.iteration == 0
    assert record.temperature == 0.0
    assert record.provider == "mock"


def test_post_prescription_transcribes_mandated_method_and_breaks():
    prescriptions = [Prescription(
        method="log_transform_then_jenks", instruction="...",
        params={"breaks": [0.5, 3.0, 6.0, 12.0, 73.0]},
    )]
    llm = MockLLM()
    proposal, _record = llm.propose(_context(prescriptions), "Map tree canopy loss")
    assert proposal.classification_method == "log_transform_then_jenks"
    assert proposal.classification_breaks == [0.5, 3.0, 6.0, 12.0, 73.0]
    assert proposal.iteration == 1


def test_two_simultaneous_prescriptions_are_both_adopted():
    """A real, previously-broken scenario: two gates (e.g. G2 on missing
    breaks, G5 on an unsafe/miscoded palette) can REJECT on the same
    iteration. Reading only prescriptions[-1] let whichever one runs later
    in GATE_ORDER silently shadow the other's fix -- its method name would
    get adopted as classification_method and the other gate's fix would be
    dropped, forcing a false non-convergence. See the matching PATCH note
    on MockLLM.propose's docstring."""
    prescriptions = [
        Prescription(
            method="quantile", instruction="fix breaks",
            params={"breaks": [15625.0, 51584.4, 71164.0, 93004.6, 130255.8, 250001.0]},
        ),
        Prescription(
            method="colorblind_safe_palette", instruction="fix palette",
            params={"palette": ["#edf8e9", "#bae4b3", "#74c476", "#31a354", "#006d2c"]},
        ),
    ]
    llm = MockLLM()
    proposal, _record = llm.propose(_context(prescriptions), "Map tree canopy loss")
    assert proposal.classification_method == "quantile"
    assert proposal.classification_breaks == [15625.0, 51584.4, 71164.0, 93004.6, 130255.8, 250001.0]
    assert proposal.palette == ["#edf8e9", "#bae4b3", "#74c476", "#31a354", "#006d2c"]


def test_two_variables_proposes_bivariate():
    ctx = SemanticContext(
        dataset_schemas=[
            FieldSchema(name="tree_canopy_loss", dtype="float64", role="density"),
            FieldSchema(name="asthma_rate", dtype="float64", role="rate"),
        ],
        aoi=AreaOfInterest(id="atl", bbox_4326=(-84.9, 33.4, -84.0, 34.1), feature_count=530),
    )
    llm = MockLLM()
    proposal, _record = llm.propose(ctx, "Map canopy loss vs asthma")
    assert proposal.map_type == "bivariate"
    assert proposal.diverging_palette is True


def test_prompt_hash_recorded_matches_context():
    ctx = _context()
    llm = MockLLM()
    _proposal, record = llm.propose(ctx, "anything")
    assert record.prompt_hash == ctx.prompt_hash()
