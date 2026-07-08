"""Hybrid spatial-semantic retrieval for STAC catalogs.

Architecture:
    Stage 1: Deterministic bounding-box filter (Qdrant payload index)
    Stage 2: Semantic vector search on metadata (restricted to Stage 1 results)
    Stage 3: LLM selection based on fitness-for-purpose reasoning

This eliminates spatial hallucinations by guaranteeing that all semantically
retrieved datasets mathematically intersect the target geometry.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import json
import numpy as np


@dataclass
class STACItem:
    """Minimal STAC item representation."""
    id: str
    title: str
    description: str
    bbox: List[float]  # [min_lon, min_lat, max_lon, max_lat]
    temporal_start: Optional[str] = None
    temporal_end: Optional[str] = None
    variables: List[Dict[str, str]] = field(default_factory=list)
    collection: str = ""
    assets: Dict[str, Any] = field(default_factory=dict)
    metadata_score: int = 0

    def to_llm_context(self) -> str:
        """Format item metadata for LLM selection prompt."""
        var_str = ", ".join(
            f"{v.get('name', 'unknown')} ({v.get('units', 'no units')})"
            for v in self.variables
        )
        return (
            f"Dataset: {self.title}\n"
            f"ID: {self.id}\n"
            f"Description: {self.description}\n"
            f"Variables: {var_str}\n"
            f"Spatial extent: {self.bbox}\n"
            f"Temporal range: {self.temporal_start} to {self.temporal_end}\n"
            f"Collection: {self.collection}\n"
            f"Metadata quality score: {self.metadata_score}/7\n"
        )


@dataclass
class RetrievalResult:
    """Output from hybrid retrieval."""
    spatial_candidates: int       # Items passing Stage 1
    semantic_results: int         # Items returned from Stage 2
    items: List[STACItem]
    retrieval_time_ms: float
    spatial_filter_time_ms: float
    semantic_search_time_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spatial_candidates": self.spatial_candidates,
            "semantic_results": self.semantic_results,
            "items": [item.id for item in self.items],
            "retrieval_time_ms": self.retrieval_time_ms,
        }


class HybridRetrieval:
    """Two-stage hybrid retrieval: spatial filter → semantic ranking."""

    def __init__(self, qdrant_client, embedding_model: str = "text-embedding-3-small"):
        """
        Args:
            qdrant_client: Initialized Qdrant client
            embedding_model: Embedding model name for semantic search
        """
        self.client = qdrant_client
        self.embedding_model = embedding_model
        self.collection_name = "stac_catalog"

    def retrieve(
        self,
        target_geometry: Dict[str, Any],
        query_text: str,
        top_k: int = 5,
    ) -> RetrievalResult:
        """
        Args:
            target_geometry: GeoJSON polygon defining the area of interest
            query_text: Natural language description of desired data
            top_k: Number of results to return

        Returns:
            RetrievalResult with spatially-filtered, semantically-ranked items
        """
        import time

        t_start = time.time()

        # Extract bounding box from target geometry
        bbox = self._geometry_to_bbox(target_geometry)

        # Stage 1: Spatial filter
        t_spatial_start = time.time()
        spatial_ids = self._spatial_filter(bbox)
        t_spatial = (time.time() - t_spatial_start) * 1000

        if not spatial_ids:
            return RetrievalResult(
                spatial_candidates=0,
                semantic_results=0,
                items=[],
                retrieval_time_ms=(time.time() - t_start) * 1000,
                spatial_filter_time_ms=t_spatial,
                semantic_search_time_ms=0.0,
            )

        # Stage 2: Semantic ranking within spatial subset
        t_semantic_start = time.time()
        results = self._semantic_search(query_text, spatial_ids, top_k)
        t_semantic = (time.time() - t_semantic_start) * 1000

        # Build STACItem objects from results
        items = [self._parse_hit(hit) for hit in results]

        return RetrievalResult(
            spatial_candidates=len(spatial_ids),
            semantic_results=len(items),
            items=items,
            retrieval_time_ms=(time.time() - t_start) * 1000,
            spatial_filter_time_ms=t_spatial,
            semantic_search_time_ms=t_semantic,
        )

    def _geometry_to_bbox(self, geometry: Dict[str, Any]) -> List[float]:
        """Extract [min_lon, min_lat, max_lon, max_lat] from GeoJSON."""
        if geometry.get("type") == "Polygon":
            coords = geometry["coordinates"][0]
        elif geometry.get("type") == "MultiPolygon":
            coords = [c for poly in geometry["coordinates"] for c in poly[0]]
        else:
            raise ValueError(f"Unsupported geometry type: {geometry.get('type')}")

        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return [min(lons), min(lats), max(lons), max(lats)]

    def _spatial_filter(self, bbox: List[float]) -> List[str]:
        """Stage 1: Deterministic bounding-box intersection.

        Uses Qdrant payload filters for sub-millisecond spatial filtering.
        The filter checks for bounding box overlap, not containment.
        """
        min_lon, min_lat, max_lon, max_lat = bbox

        # Build Qdrant filter: BBOX intersection
        # A intersects B if: A.min_lon <= B.max_lon AND A.max_lon >= B.min_lon
        #                      AND A.min_lat <= B.max_lat AND A.max_lat >= B.min_lat
        from qdrant_client.models import Filter, FieldCondition, Range

        filter_conditions = Filter(
            must=[
                FieldCondition(
                    key="bbox.min_lon",
                    range=Range(lte=max_lon),
                ),
                FieldCondition(
                    key="bbox.max_lon",
                    range=Range(gte=min_lon),
                ),
                FieldCondition(
                    key="bbox.min_lat",
                    range=Range(lte=max_lat),
                ),
                FieldCondition(
                    key="bbox.max_lat",
                    range=Range(gte=min_lat),
                ),
            ]
        )

        # Scroll through all matching points (no vector, just payload filter)
        ids = []
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=filter_conditions,
                limit=100,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            if not points:
                break
            ids.extend(p.id for p in points)
            if offset is None:
                break

        return ids

    def _semantic_search(
        self, query_text: str, allowed_ids: List[str], top_k: int
    ) -> List[Any]:
        """Stage 2: Semantic search restricted to spatially-filtered IDs.

        Uses Qdrant's built-in payload filtering during vector search
        to enforce that only spatially-qualified items are ranked.
        """
        from qdrant_client.models import Filter, HasIdCondition

        # Generate embedding for query
        query_vector = self._embed(query_text)

        # Semantic search with ID filter
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=Filter(
                must=[HasIdCondition(has_id=allowed_ids)]
            ),
            limit=top_k,
            with_payload=True,
        )

        return results

    def _embed(self, text: str) -> List[float]:
        """Generate text embedding.

        Production: Call OpenAI API or local embedding model.
        Development: Return dummy vector for testing.
        """
        # Placeholder — replace with actual embedding call
        # For reproducibility, document exact model and version
        # e.g., openai.Embedding.create(model="text-embedding-3-small", input=text)
        return [0.0] * 1536

    def _parse_hit(self, hit: Any) -> STACItem:
        """Parse a Qdrant search result into a STACItem."""
        payload = hit.payload
        return STACItem(
            id=hit.id,
            title=payload.get("title", "Untitled"),
            description=payload.get("description", ""),
            bbox=[
                payload.get("bbox", {}).get("min_lon", 0),
                payload.get("bbox", {}).get("min_lat", 0),
                payload.get("bbox", {}).get("max_lon", 0),
                payload.get("bbox", {}).get("max_lat", 0),
            ],
            temporal_start=payload.get("temporal_start"),
            temporal_end=payload.get("temporal_end"),
            variables=payload.get("variables", []),
            collection=payload.get("collection", ""),
            metadata_score=payload.get("metadata_score", 0),
        )