"""STAC catalog indexer — Blueprint §6.2 P3-T1.

Ingests a list of `STACItem`s into a real Qdrant collection with bbox
payload fields and a deterministic point-ID mapping. Two real-Qdrant
constraints this module exists to handle correctly (both verified against
a live local instance, not assumed from documentation):

1. **Point IDs must be an unsigned integer or a UUID** — an arbitrary
   string like ``"atl-canopy"`` is rejected at upsert time (400 Bad
   Request). Each item's real catalog ID is preserved in
   ``payload["stac_id"]`` and mapped to a *deterministic* UUID5 (so
   re-indexing the same catalog produces the same point IDs, not random
   new ones) via ``stac_id_to_point_id``.
2. **Antimeridian-crossing items must be pre-split, not indexed whole** —
   `hybrid_retrieval.py` already handles antimeridian *queries* by
   splitting the query AOI into east/west shards (reviewer patch R2-2).
   That only works if antimeridian-crossing *catalog items* were indexed
   the same way. `index_items` enforces this at ingest time: an item whose
   bbox spans more than 180 degrees of longitude is rejected with an
   actionable error instead of being silently indexed as an unqueryable
   bad bbox.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Optional, Sequence

from autocarto.data_fabric.hybrid_retrieval import STACItem, _hash_embedding

_UUID_NAMESPACE = uuid.NAMESPACE_URL


def stac_id_to_point_id(stac_id: str) -> str:
    """Deterministic UUID5 for a STAC item ID — stable across re-indexing."""
    return str(uuid.uuid5(_UUID_NAMESPACE, stac_id))


class AntimeridianCrossingError(ValueError):
    """Raised when a catalog item's bbox spans the antimeridian unsplit."""


def _validate_no_antimeridian_crossing(item: STACItem) -> None:
    min_lon, _min_lat, max_lon, _max_lat = item.bbox
    if (max_lon - min_lon) > 180:
        raise AntimeridianCrossingError(
            f"Item {item.id!r} has a bbox spanning {max_lon - min_lon:.1f} "
            f"degrees of longitude ({min_lon} to {max_lon}), which crosses "
            f"the antimeridian. Index it as two separate items instead (an "
            f"east shard ending at 180.0 and a west shard starting at "
            f"-180.0) — see hybrid_retrieval.py's antimeridian handling "
            f"(reviewer patch R2-2) and demo.py's "
            f"make_mock_catalog_with_aleutians for the convention."
        )


def _item_to_payload(item: STACItem) -> Dict[str, Any]:
    return {
        "stac_id": item.id,
        "title": item.title,
        "description": item.description,
        "bbox": {
            "min_lon": item.bbox[0], "min_lat": item.bbox[1],
            "max_lon": item.bbox[2], "max_lat": item.bbox[3],
        },
        "temporal_start": item.temporal_start,
        "temporal_end": item.temporal_end,
        "variables": item.variables,
        "collection": item.collection,
        "metadata_score": item.metadata_score,
        "geometry": item.geometry,
        "license": item.license,
        "lineage": item.lineage,
    }


def ensure_collection(client: Any, collection_name: str, vector_size: int) -> None:
    """Create the collection if it doesn't already exist (idempotent)."""
    from qdrant_client.models import Distance, VectorParams

    if client.collection_exists(collection_name):
        return
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def index_items(
    client: Any,
    items: Sequence[STACItem],
    *,
    collection_name: str = "stac_catalog",
    embedder: Optional[Callable[[str], List[float]]] = None,
    vector_size: int = 1536,
) -> List[str]:
    """Index STAC items into a (real) Qdrant collection.

    Args:
        client: a live qdrant_client.QdrantClient (or compatible)
        items: catalog items to index
        collection_name: must match the value HybridRetrieval was
            constructed to query (HybridRetrieval.collection_name)
        embedder: text -> vector callable; defaults to the deterministic
            hash embedding used everywhere else in this project when no
            real embedder is injected (air-gap-safe, no network call)
        vector_size: must match embedder's output dimension

    Returns:
        The list of point IDs written (UUID5 strings, one per item).

    Raises:
        AntimeridianCrossingError: an item's bbox crosses the antimeridian
            unsplit — fix the catalog rather than indexing a bad bbox.
    """
    from qdrant_client.models import PointStruct

    for item in items:
        _validate_no_antimeridian_crossing(item)

    embed = embedder or (lambda text: _hash_embedding(text, dim=vector_size))

    ensure_collection(client, collection_name, vector_size)

    point_ids: List[str] = []
    points = []
    for item in items:
        point_id = stac_id_to_point_id(item.id)
        point_ids.append(point_id)
        embed_text = f"{item.title} {item.description} " + " ".join(
            v.get("name", "") for v in item.variables
        )
        points.append(PointStruct(
            id=point_id,
            vector=embed(embed_text.strip()),
            payload=_item_to_payload(item),
        ))

    client.upsert(collection_name=collection_name, points=points)
    return point_ids
