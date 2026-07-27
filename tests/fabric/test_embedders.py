"""Real embedder tests — Blueprint §6.2 P3-T4.

Proves the property that actually matters and that the hash-embedding
fallback cannot provide: semantically related text should score higher
cosine similarity than unrelated text. The hash fallback is intentionally
blind to meaning (SHA256-seeded noise) — this is the upgrade path.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("sentence_transformers")

from autocarto.data_fabric.embedders import SentenceTransformerEmbedder
from autocarto.data_fabric.hybrid_retrieval import HybridRetrieval, _hash_embedding
from autocarto.demo import MockQdrantClient, make_mock_catalog


@pytest.fixture(scope="module")
def embedder():
    return SentenceTransformerEmbedder()


def _cosine(a, b):
    a, b = np.array(a), np.array(b)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def test_embeddings_are_unit_norm(embedder):
    vec = embedder("tree canopy loss vegetation")
    assert abs(np.linalg.norm(vec) - 1.0) < 1e-5


def test_dimension_matches_model_output(embedder):
    vec = embedder("test")
    assert len(vec) == embedder.dimension
    assert embedder.dimension > 0


def test_semantically_related_text_scores_higher_than_unrelated(embedder):
    canopy = embedder("tree canopy loss vegetation urban heat")
    wildfire = embedder("wildfire burn severity vegetation forest")  # related: both vegetation
    asthma = embedder("asthma respiratory health hospitalization")   # unrelated topic

    sim_related = _cosine(canopy, wildfire)
    sim_unrelated = _cosine(canopy, asthma)
    assert sim_related > sim_unrelated


def test_deterministic_across_calls(embedder):
    """Same model, same text -> same vector (no sampling/randomness)."""
    v1 = embedder("tree canopy loss")
    v2 = embedder("tree canopy loss")
    assert np.allclose(v1, v2)


def test_hash_embedding_has_no_semantic_signal_by_contrast():
    """Documents *why* the real embedder is worth the dependency: the hash
    fallback's similarity is unrelated to actual meaning."""
    canopy = _hash_embedding("tree canopy loss vegetation urban heat")
    wildfire = _hash_embedding("wildfire burn severity vegetation forest")
    asthma = _hash_embedding("asthma respiratory health hospitalization")
    sim_related = _cosine(canopy, wildfire)
    sim_unrelated = _cosine(canopy, asthma)
    # Both are small and essentially noise -- no reliable ordering. This
    # test documents the limitation rather than asserting a direction.
    assert abs(sim_related) < 0.15 and abs(sim_unrelated) < 0.15


def test_plugs_into_hybrid_retrieval_via_existing_injection_point(embedder):
    """The whole point: HybridRetrieval's embedder= parameter already
    existed (original review) specifically for this — no retrieval-layer
    changes were needed to use a real embedder, only this adapter.

    Catalog items here are embedded with the *same* real embedder
    (384-dim), not make_mock_catalog()'s hash embeddings (1536-dim) —
    switching embedders means re-indexing with matching dimensions, same
    as a real Qdrant collection would require (verified: mixing the two
    raises a dimension-mismatch error, which is correct, not a bug to
    paper over).
    """
    def build_item(item_id, title, desc, bbox, embed_text):
        return {
            "id": item_id, "vector": embedder(embed_text),
            "payload": {"title": title, "description": desc, "bbox": bbox,
                       "variables": [], "collection": "test", "metadata_score": 5},
        }

    catalog = [
        build_item("atl-canopy", "Atlanta Tree Canopy Loss",
                   "Annual tree canopy cover loss per census tract in metro Atlanta.",
                   {"min_lon": -84.6, "min_lat": 33.6, "max_lon": -84.2, "max_lat": 34.0},
                   "tree canopy loss vegetation urban heat"),
        build_item("cdc-asthma", "CDC PLACES Asthma Rate",
                   "Age-adjusted asthma hospitalisation rate per census tract.",
                   {"min_lon": -84.6, "min_lat": 33.6, "max_lon": -84.2, "max_lat": 34.0},
                   "respiratory health asthma hospitalisation public health tract"),
        build_item("atl-noise", "Sensor data 2019", "",
                   {"min_lon": -84.6, "min_lat": 33.6, "max_lon": -84.2, "max_lat": 34.0},
                   "noise sensor"),
    ]

    calls = []

    def wrapped(text):
        calls.append(text)
        return embedder(text)

    retrieval = HybridRetrieval(MockQdrantClient(catalog), embedder=wrapped)
    atlanta = {
        "type": "Polygon",
        "coordinates": [[
            [-84.6, 33.6], [-84.2, 33.6], [-84.2, 34.0], [-84.6, 34.0], [-84.6, 33.6],
        ]],
    }
    result = retrieval.retrieve(atlanta, "respiratory health and air quality", top_k=3)
    assert len(calls) == 1  # embedder invoked exactly once for the query
    # With real semantics, the asthma dataset should rank above the noisy
    # low-quality sensor item for a health-related query.
    ids_in_order = [it.id for it in result.items]
    assert "cdc-asthma" in ids_in_order
    assert ids_in_order.index("cdc-asthma") < ids_in_order.index("atl-noise")
