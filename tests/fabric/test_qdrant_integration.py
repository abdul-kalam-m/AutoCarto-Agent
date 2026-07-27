"""Real-Qdrant integration tests — Blueprint §6.2 P3-T1.

Everything else in tests/fabric/ exercises HybridRetrieval against
MockQdrantClient. These tests run the *same* HybridRetrieval class against
a genuine, live Qdrant instance via stac_indexer.py — the thing the mock
was always meant to stand in for. They exist because building the real
integration surfaced a real bug: current qdrant-client (>=1.10) has no
`.search()` method (replaced by `.query_points()`), which the mock's
hand-written `.search()` shape never would have caught.

Skipped automatically if no reachable Qdrant instance is configured via
the AUTOCARTO_QDRANT_URL env var (default: http://localhost:16333, the
port this test suite's local dev container was started on) — this is
network-dependent, opt-in test infrastructure, not something CI or a
fresh clone should require.
"""

from __future__ import annotations

import os
import uuid

import pytest

qdrant_client = pytest.importorskip("qdrant_client")

from autocarto.data_fabric.hybrid_retrieval import STACItem, HybridRetrieval
from autocarto.data_fabric.stac_indexer import (
    AntimeridianCrossingError,
    index_items,
    stac_id_to_point_id,
)

QDRANT_URL = os.environ.get("AUTOCARTO_QDRANT_URL", "http://localhost:16333")
VECTOR_SIZE = 64  # small for fast tests; real deployments would match the embedder


def _get_client():
    from qdrant_client import QdrantClient
    client = QdrantClient(url=QDRANT_URL, timeout=3)
    client.get_collections()  # raises if unreachable
    return client


try:
    _client_available = True
    _get_client()
except Exception:
    _client_available = False

pytestmark = pytest.mark.skipif(
    not _client_available,
    reason=f"no reachable Qdrant at {QDRANT_URL} (set AUTOCARTO_QDRANT_URL or start one)",
)


def _sample_catalog():
    return [
        STACItem(
            id="atl-canopy", title="Atlanta Tree Canopy Loss",
            description="Annual tree canopy cover loss per census tract in metro Atlanta.",
            bbox=[-84.6, 33.6, -84.2, 34.0],
            variables=[{"name": "canopy_loss_pct", "units": "percent"}],
            temporal_start="2015-01-01", temporal_end="2022-12-31",
        ),
        STACItem(
            id="la-wildfire", title="California MTBS Wildfire Perimeters",
            description="Wildfire burn severity perimeters, California.",
            bbox=[-124.5, 32.5, -114.1, 42.0],
            variables=[{"name": "burn_severity", "units": "ordinal"}],
        ),
        STACItem(
            id="nyc-vision-zero", title="NYC Vision Zero Pedestrian Injuries",
            description="Per-intersection pedestrian injury counts, NYC.",
            bbox=[-74.05, 40.68, -73.90, 40.88],
            variables=[{"name": "pedestrian_injuries", "units": "count"}],
        ),
    ]


@pytest.fixture()
def indexed_retrieval():
    """Index the sample catalog into a uniquely-named collection, yield a
    HybridRetrieval wired to it, then delete the collection afterward."""
    client = _get_client()
    collection_name = f"autocarto-test-{uuid.uuid4().hex[:8]}"
    index_items(client, _sample_catalog(), collection_name=collection_name, vector_size=VECTOR_SIZE)

    retrieval = HybridRetrieval(client, embedder=lambda t: _fixed_dim_hash(t))
    retrieval.collection_name = collection_name
    try:
        yield retrieval
    finally:
        client.delete_collection(collection_name)


def _fixed_dim_hash(text: str):
    from autocarto.data_fabric.hybrid_retrieval import _hash_embedding
    return _hash_embedding(text, dim=VECTOR_SIZE)


ATLANTA_AOI = {
    "type": "Polygon",
    "coordinates": [[
        [-84.55, 33.65], [-84.25, 33.65],
        [-84.25, 33.95], [-84.55, 33.95],
        [-84.55, 33.65],
    ]],
}


def test_real_qdrant_spatial_filter_excludes_out_of_aoi_items(indexed_retrieval):
    result = indexed_retrieval.retrieve(ATLANTA_AOI, "tree canopy loss vegetation", top_k=5)
    ids = {it.id for it in result.items}
    assert "atl-canopy" in ids
    assert "la-wildfire" not in ids
    assert "nyc-vision-zero" not in ids
    assert result.spatial_candidates == 1


def test_real_qdrant_semantic_ranking_returns_real_stac_ids(indexed_retrieval):
    """Round-trip check: point IDs are UUID5s internally, but STACItem.id
    on the way out must be the original catalog string ID."""
    result = indexed_retrieval.retrieve(ATLANTA_AOI, "canopy loss", top_k=5)
    assert len(result.items) >= 1
    for item in result.items:
        assert item.id == "atl-canopy"  # not the internal UUID
        uuid.UUID(stac_id_to_point_id(item.id))  # sanity: mapping is a valid UUID


def test_real_qdrant_empty_region_returns_empty(indexed_retrieval):
    ocean = {
        "type": "Polygon",
        "coordinates": [[
            [-40.0, 30.0], [-39.0, 30.0], [-39.0, 31.0], [-40.0, 31.0], [-40.0, 30.0],
        ]],
    }
    result = indexed_retrieval.retrieve(ocean, "anything", top_k=5)
    assert result.spatial_candidates == 0
    assert result.items == []


def test_antimeridian_crossing_item_rejected_at_index_time():
    client = _get_client()
    bad_item = STACItem(
        id="bad-aleutian-unsplit", title="Aleutian (should be split)",
        description="Deliberately crosses the antimeridian without pre-splitting.",
        # A naive min()/max() over antimeridian-crossing vertices (e.g. 172
        # and -164) computes min_lon=-164, max_lon=172 -- a 336-degree span
        # that misreads a ~24-degree true crossing as spanning the "long
        # way" around the globe. This is exactly the bug the check catches.
        bbox=[-164.0, 51.0, 172.0, 55.0],
    )
    with pytest.raises(AntimeridianCrossingError):
        index_items(client, [bad_item], collection_name="autocarto-test-should-not-exist", vector_size=VECTOR_SIZE)


def test_reindexing_same_catalog_produces_stable_point_ids():
    """Point IDs are deterministic (UUID5), not random -- re-indexing the
    same catalog must upsert into the same points, not duplicate them."""
    client = _get_client()
    collection_name = f"autocarto-test-stable-{uuid.uuid4().hex[:8]}"
    try:
        ids_1 = index_items(client, _sample_catalog(), collection_name=collection_name, vector_size=VECTOR_SIZE)
        ids_2 = index_items(client, _sample_catalog(), collection_name=collection_name, vector_size=VECTOR_SIZE)
        assert ids_1 == ids_2
        count = client.count(collection_name=collection_name).count
        assert count == len(_sample_catalog())  # no duplicates from re-indexing
    finally:
        client.delete_collection(collection_name)
