"""Hybrid retrieval contracts: spatial-first filtering, antimeridian, geometry types."""

from __future__ import annotations

import pytest

from autocarto.data_fabric.hybrid_retrieval import HybridRetrieval, _hash_embedding
from autocarto.demo import (
    MockQdrantClient,
    make_mock_catalog,
    make_mock_catalog_with_aleutians,
)


@pytest.fixture()
def retrieval():
    return HybridRetrieval(MockQdrantClient(make_mock_catalog_with_aleutians()))


ATLANTA = {
    "type": "Polygon",
    "coordinates": [[
        [-84.55, 33.65], [-84.25, 33.65],
        [-84.25, 33.95], [-84.55, 33.95],
        [-84.55, 33.65],
    ]],
}

ALEUTIAN = {  # crosses the antimeridian: lons run 172 … 180 / −180 … −164
    "type": "Polygon",
    "coordinates": [[
        [172.0, 51.5], [180.0, 51.5],
        [-180.0, 51.5], [-164.0, 51.5],
        [-164.0, 54.5], [172.0, 54.5],
        [172.0, 51.5],
    ]],
}


def test_spatial_filter_runs_before_semantic_ranking(retrieval):
    """Items outside the AOI must be excluded regardless of semantic score."""
    result = retrieval.retrieve(ATLANTA, "wildfire burn severity vegetation", top_k=5)
    ids = [it.id for it in result.items]
    # la-wildfire is the best semantic match for this query but lies in CA:
    assert "la-wildfire" not in ids
    assert result.spatial_candidates == 3          # atl-canopy, atl-noise, cdc-asthma


def test_atlanta_query_returns_spatially_valid_items(retrieval):
    result = retrieval.retrieve(ATLANTA, "Atlanta tree canopy and respiratory health", top_k=3)
    assert result.spatial_candidates == 3
    assert {it.id for it in result.items} == {"atl-canopy", "atl-noise", "cdc-asthma"}


def test_antimeridian_polygon_finds_both_shards(retrieval):
    """Reviewer patch R2-2: naive bbox logic returns zero results here."""
    result = retrieval.retrieve(ALEUTIAN, "seabird habitat coastal alaska", top_k=5)
    assert {it.id for it in result.items} == {
        "aleutian-seabird-east", "aleutian-seabird-west"
    }


def test_point_geometry_supported(retrieval):
    point = {"type": "Point", "coordinates": [-84.39, 33.75]}   # downtown Atlanta
    result = retrieval.retrieve(point, "tree canopy", top_k=5)
    assert result.spatial_candidates >= 1
    assert "atl-canopy" in {it.id for it in result.items}


def test_multipolygon_with_hole_uses_outer_envelope(retrieval):
    donut = {
        "type": "MultiPolygon",
        "coordinates": [[
            # outer ring around Atlanta
            [[-84.6, 33.6], [-84.2, 33.6], [-84.2, 34.0], [-84.6, 34.0], [-84.6, 33.6]],
            # interior ring (hole) — must not shrink the envelope
            [[-84.45, 33.75], [-84.35, 33.75], [-84.35, 33.85], [-84.45, 33.85], [-84.45, 33.75]],
        ]],
    }
    result = retrieval.retrieve(donut, "tree canopy", top_k=5)
    assert "atl-canopy" in {it.id for it in result.items}


def test_empty_region_returns_empty_not_error(retrieval):
    mid_atlantic_ocean = {
        "type": "Polygon",
        "coordinates": [[
            [-40.0, 30.0], [-39.0, 30.0], [-39.0, 31.0], [-40.0, 31.0], [-40.0, 30.0],
        ]],
    }
    result = retrieval.retrieve(mid_atlantic_ocean, "anything", top_k=5)
    assert result.spatial_candidates == 0
    assert result.items == []


def test_hash_embedding_deterministic_and_unit_norm():
    import numpy as np
    v1 = np.array(_hash_embedding("tree canopy"))
    v2 = np.array(_hash_embedding("tree canopy"))
    v3 = np.array(_hash_embedding("asthma"))
    assert np.array_equal(v1, v2)
    assert not np.array_equal(v1, v3)
    assert abs(np.linalg.norm(v1) - 1.0) < 1e-9


def test_injected_embedder_is_used():
    calls = []

    def fake_embedder(text):
        calls.append(text)
        return _hash_embedding(text)

    r = HybridRetrieval(MockQdrantClient(make_mock_catalog()), embedder=fake_embedder)
    r.retrieve(ATLANTA, "tree canopy", top_k=2)
    assert calls == ["tree canopy"]
