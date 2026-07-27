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
