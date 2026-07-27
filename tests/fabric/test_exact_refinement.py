"""Exact geometric refinement (Stage 1.5) tests — Blueprint §6.2 C7'.

Bbox envelope overlap is necessary but not sufficient for true spatial
intersection: an L-shaped or diagonal dataset footprint can have a bounding
box that overlaps a query AOI while the actual polygon does not. These
tests prove the refinement stage catches that case (and doesn't break
plain-bbox catalog items that carry no stored footprint).
"""

from __future__ import annotations

import pytest

from autocarto.data_fabric.hybrid_retrieval import HybridRetrieval, _hash_embedding
from autocarto.demo import MockQdrantClient

# A query AOI: a 1x1 degree box in the "empty corner" of an L-shaped dataset's
# bounding box, but outside the dataset's actual L-shaped footprint.
QUERY_AOI = {
    "type": "Polygon",
    "coordinates": [[
        [3.0, 3.0], [4.0, 3.0], [4.0, 4.0], [3.0, 4.0], [3.0, 3.0],
    ]],
}

# L-shaped real footprint: covers the bottom row and left column of a 5x5
# grid, but NOT the top-right cell where QUERY_AOI sits. Its bbox is [0,0,5,5]
# -- which DOES overlap QUERY_AOI -- so only exact refinement catches this.
L_SHAPE_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[
        [0.0, 0.0], [5.0, 0.0], [5.0, 1.0], [1.0, 1.0],
        [1.0, 5.0], [0.0, 5.0], [0.0, 0.0],
    ]],
}


def _catalog_with_l_shape():
    return [
        {
            "id": "l-shaped-dataset",
            "vector": _hash_embedding("a dataset with an L-shaped footprint"),
            "payload": {
                "title": "L-shaped coverage dataset",
                "description": "Covers only the bottom row and left column of its bbox.",
                "bbox": {"min_lon": 0.0, "min_lat": 0.0, "max_lon": 5.0, "max_lat": 5.0},
                "geometry": L_SHAPE_GEOMETRY,
                "temporal_start": None, "temporal_end": None,
                "variables": [], "collection": "test", "metadata_score": 5,
            },
        },
        {
            "id": "bbox-only-dataset",
            # Same bbox, but NO geometry field -- envelope-only assurance,
            # must pass through refinement unfiltered (nothing to refine).
            "vector": _hash_embedding("a bbox-only legacy catalog entry"),
            "payload": {
                "title": "Legacy bbox-only dataset",
                "description": "No stored footprint polygon.",
                "bbox": {"min_lon": 0.0, "min_lat": 0.0, "max_lon": 5.0, "max_lat": 5.0},
                "temporal_start": None, "temporal_end": None,
                "variables": [], "collection": "test", "metadata_score": 5,
            },
        },
    ]


def test_envelope_overlap_without_true_intersection_is_filtered():
    retrieval = HybridRetrieval(MockQdrantClient(_catalog_with_l_shape()))
    result = retrieval.retrieve(QUERY_AOI, "L-shaped dataset", top_k=5)

    # Envelope (Stage 1) sees both items -- their bboxes both overlap the AOI.
    assert result.envelope_candidates == 2
    # Exact refinement drops the L-shaped item (true footprint does not
    # reach the query AOI's corner) but keeps the bbox-only item (nothing
    # to refine against -- envelope-only assurance, honestly reported).
    assert result.spatial_candidates == 1
    ids = {it.id for it in result.items}
    assert "l-shaped-dataset" not in ids
    assert "bbox-only-dataset" in ids


def test_true_intersection_with_l_shape_is_kept():
    """A query AOI that actually lands inside the L's real footprint (the
    bottom-left cell) must still be returned -- refinement isn't just a
    blanket filter, it tests real geometry."""
    inside_l = {
        "type": "Polygon",
        "coordinates": [[[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8], [0.2, 0.2]]],
    }
    retrieval = HybridRetrieval(MockQdrantClient(_catalog_with_l_shape()))
    result = retrieval.retrieve(inside_l, "L-shaped dataset", top_k=5)
    assert "l-shaped-dataset" in {it.id for it in result.items}


class _NoRetrieveClient:
    """Exposes only scroll()/search(), deliberately no .retrieve() -- an
    isolated stand-in (not a MockQdrantClient subclass/mutation) simulating
    an older/minimal Qdrant client that lacks by-ID payload fetch."""

    def __init__(self, items):
        self._inner = MockQdrantClient(items)

    def scroll(self, *args, **kwargs):
        return self._inner.scroll(*args, **kwargs)

    def search(self, *args, **kwargs):
        return self._inner.search(*args, **kwargs)


def test_refinement_degrades_gracefully_without_retrieve_support():
    """A client with no .retrieve() method must not crash retrieval --
    refinement is skipped and envelope-only behavior is preserved
    (pre-P3-T2 behavior), not a hard failure."""
    client = _NoRetrieveClient(_catalog_with_l_shape())
    retrieval = HybridRetrieval(client)
    result = retrieval.retrieve(QUERY_AOI, "L-shaped dataset", top_k=5)
    # Without refinement capability, both bbox-overlapping items pass through.
    assert result.spatial_candidates == 2
