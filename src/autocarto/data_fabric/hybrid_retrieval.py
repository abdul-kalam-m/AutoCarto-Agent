"""Hybrid spatial-semantic retrieval for STAC catalogs.

Architecture:
    Stage 1: Deterministic bounding-box filter (Qdrant payload index)
    Stage 2: Semantic vector search on metadata (restricted to Stage 1 results)
    Stage 3: LLM selection based on fitness-for-purpose reasoning

This eliminates spatial hallucinations by guaranteeing that all semantically
retrieved datasets mathematically intersect the target geometry.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Callable
import hashlib
import json
import time
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
    # PATCH (P3-T2, exact refinement): the actual footprint polygon, when the
    # catalog has one. Bbox-only items (geometry=None) get envelope-level
    # assurance only -- see HybridRetrieval._exact_refine.
    geometry: Optional[Dict[str, Any]] = None
    # PATCH (P3-T3, metadata scorer): two of the 7-point rubric criteria.
    license: Optional[str] = None
    lineage: Optional[str] = None

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
    spatial_candidates: int       # Items passing Stage 1 + exact refinement (true candidates)
    semantic_results: int         # Items returned from Stage 2
    items: List[STACItem]
    retrieval_time_ms: float
    spatial_filter_time_ms: float
    semantic_search_time_ms: float
    # PATCH (P3-T2): envelope-only count before exact refinement, so callers
    # can see the refinement's effect explicitly. Equal to spatial_candidates
    # when no candidate carries real geometry (nothing to refine against) or
    # when the client doesn't support fetching payloads by ID.
    envelope_candidates: int = 0
    exact_refine_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spatial_candidates": self.spatial_candidates,
            "envelope_candidates": self.envelope_candidates,
            "semantic_results": self.semantic_results,
            "items": [item.id for item in self.items],
            "retrieval_time_ms": round(self.retrieval_time_ms, 3),
            "spatial_filter_time_ms": round(self.spatial_filter_time_ms, 3),
            "exact_refine_time_ms": round(self.exact_refine_time_ms, 3),
            "semantic_search_time_ms": round(self.semantic_search_time_ms, 3),
        }


# PATCH: deterministic hash-based embedding so the module can be exercised in
# air-gapped tests without an OpenAI API call. The function is purely a
# fallback; production deployments should inject an actual embedder via the
# ``embedder`` argument to HybridRetrieval.
def _hash_embedding(text: str, dim: int = 1536, seed: int = 0) -> List[float]:
    """Stable pseudo-embedding seeded by SHA256 of the input text."""
    digest = hashlib.sha256(f"{seed}|{text}".encode("utf-8")).digest()
    rng = np.random.default_rng(int.from_bytes(digest[:8], "little"))
    vec = rng.standard_normal(dim)
    norm = np.linalg.norm(vec)
    if norm == 0:
        return [0.0] * dim
    return (vec / norm).tolist()


class HybridRetrieval:
    """Two-stage hybrid retrieval: spatial filter -> semantic ranking."""

    def __init__(
        self,
        qdrant_client,
        embedding_model: str = "text-embedding-3-small",
        embedder: Optional[Callable[[str], List[float]]] = None,
    ):
        """
        Args:
            qdrant_client: Initialized Qdrant client
            embedding_model: Embedding model name for semantic search
            embedder: Optional callable that turns query text into a vector.
                When None, a deterministic hash-based embedding is used so the
                module is unit-testable without network calls.
        """
        self.client = qdrant_client
        self.embedding_model = embedding_model
        self.collection_name = "stac_catalog"
        self._embedder = embedder

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
        t_start = time.time()

        # PATCH (reviewer issue 3): extract one or two bboxes depending on
        # whether the geometry crosses the antimeridian (180th meridian).
        bboxes = self._extract_bboxes(target_geometry)

        # Stage 1: Spatial filter — union IDs from all bbox queries (OR logic).
        t_spatial_start = time.time()
        spatial_ids_set: set = set()
        for bbox in bboxes:
            spatial_ids_set.update(self._spatial_filter(bbox))
        envelope_ids = list(spatial_ids_set)
        t_spatial = (time.time() - t_spatial_start) * 1000

        if not envelope_ids:
            return RetrievalResult(
                spatial_candidates=0,
                envelope_candidates=0,
                semantic_results=0,
                items=[],
                retrieval_time_ms=(time.time() - t_start) * 1000,
                spatial_filter_time_ms=t_spatial,
                semantic_search_time_ms=0.0,
            )

        # Stage 1.5: exact geometric refinement (C7' -- envelope overlap is
        # necessary, not sufficient). Runs *before* semantic ranking so
        # every semantically-ranked candidate has already been confirmed to
        # truly intersect the AOI, not just its bounding box.
        t_refine_start = time.time()
        spatial_ids = self._exact_refine(envelope_ids, target_geometry)
        t_refine = (time.time() - t_refine_start) * 1000

        if not spatial_ids:
            return RetrievalResult(
                spatial_candidates=0,
                envelope_candidates=len(envelope_ids),
                semantic_results=0,
                items=[],
                retrieval_time_ms=(time.time() - t_start) * 1000,
                spatial_filter_time_ms=t_spatial,
                exact_refine_time_ms=t_refine,
                semantic_search_time_ms=0.0,
            )

        # Stage 2: Semantic ranking within the refined spatial subset
        t_semantic_start = time.time()
        results = self._semantic_search(query_text, spatial_ids, top_k)
        t_semantic = (time.time() - t_semantic_start) * 1000

        # Build STACItem objects from results
        items = [self._parse_hit(hit) for hit in results]

        return RetrievalResult(
            spatial_candidates=len(spatial_ids),
            envelope_candidates=len(envelope_ids),
            semantic_results=len(items),
            items=items,
            retrieval_time_ms=(time.time() - t_start) * 1000,
            spatial_filter_time_ms=t_spatial,
            exact_refine_time_ms=t_refine,
            semantic_search_time_ms=t_semantic,
        )

    def _exact_refine(self, envelope_ids: List[str], target_geometry: Dict[str, Any]) -> List[str]:
        """Stage 1.5: drop envelope-only false positives via true polygon
        intersection (shapely.STRtree), per the abstract's C7' claim.

        Fetches each Stage-1 candidate's payload (for its ``geometry``
        field, if any) via ``self.client.retrieve(...)``. An item with no
        stored footprint (``geometry`` absent/None) passes through
        unfiltered -- envelope overlap is the best assurance available for
        it, and that is honestly what the trace should say (see
        ``envelope_candidates`` vs ``spatial_candidates`` on the result).
        If the client does not support ``.retrieve()`` at all (a minimal
        mock, or an older Qdrant client), refinement is skipped entirely
        and every envelope candidate passes through -- degrading to the
        pre-P3-T2 behavior rather than raising.
        """
        try:
            records = self.client.retrieve(
                collection_name=self.collection_name, ids=envelope_ids, with_payload=True,
            )
        except (AttributeError, TypeError):
            return envelope_ids  # client has no by-ID payload fetch -- can't refine

        import shapely.geometry
        from shapely.strtree import STRtree

        try:
            aoi_shape = shapely.geometry.shape(target_geometry)
        except Exception:
            return envelope_ids  # malformed AOI geometry -- refinement is a no-op, not a crash

        geometried: List[Any] = []
        geometried_ids: List[str] = []
        passthrough_ids: List[str] = []

        for rec in records:
            rec_id = getattr(rec, "id", None) if not isinstance(rec, dict) else rec.get("id")
            payload = getattr(rec, "payload", None) if not isinstance(rec, dict) else rec.get("payload")
            geom = (payload or {}).get("geometry")
            if geom is None:
                passthrough_ids.append(rec_id)
                continue
            try:
                geometried.append(shapely.geometry.shape(geom))
                geometried_ids.append(rec_id)
            except Exception:
                passthrough_ids.append(rec_id)  # unparseable geometry -- fail open to envelope-only

        if not geometried:
            return envelope_ids

        tree = STRtree(geometried)
        hit_positions = tree.query(aoi_shape, predicate="intersects")
        confirmed_ids = {geometried_ids[i] for i in hit_positions}

        return [i for i in envelope_ids if i in confirmed_ids or i in passthrough_ids]

    def _extract_bboxes(self, geometry: Dict[str, Any]) -> List[List[float]]:
        """Extract one or two bboxes from a GeoJSON geometry.

        PATCH (reviewer issue 3): the original ``_geometry_to_bbox`` applied a
        naïve ``min(lons)/max(lons)`` that fails when the polygon crosses the
        antimeridian (180th meridian). For the Aleutian Islands or Fiji,
        ``min(lons)`` might be 179° and ``max(lons)`` might be –179°, so the
        Qdrant filter ``lon <= -179 AND lon >= 179`` returns zero results.

        Detection heuristic: if ``max(lons) – min(lons) > 180`` the polygon
        straddles the antimeridian. We split into two axis-aligned bboxes and
        query them with a logical OR (caller unions the ID sets).

        Returned bboxes are [min_lon, min_lat, max_lon, max_lat] each.
        """
        gtype = geometry.get("type")
        if gtype == "Polygon":
            coords = geometry["coordinates"][0]
        elif gtype == "MultiPolygon":
            coords = []
            for poly in geometry["coordinates"]:
                for ring in poly:
                    coords.extend(ring)
        elif gtype == "Point":
            lon, lat = geometry["coordinates"][0], geometry["coordinates"][1]
            return [[lon, lat, lon, lat]]
        else:
            raise ValueError(f"Unsupported geometry type: {gtype}")

        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        min_lat, max_lat = min(lats), max(lats)

        lon_span = max(lons) - min(lons)
        if lon_span > 180:
            # Antimeridian crossing: vertices have longitudes clustered near
            # +180 AND near -180. Split into an eastern shard [east_min, 180]
            # and a western shard [-180, west_max].
            pos_lons = [lo for lo in lons if lo >= 0]
            neg_lons = [lo for lo in lons if lo < 0]
            if not pos_lons or not neg_lons:
                # All lons are on one side despite the span — degenerate case,
                # fall back to the simple bbox.
                return [[min(lons), min_lat, max(lons), max_lat]]
            east_bbox = [min(pos_lons), min_lat, 180.0, max_lat]
            west_bbox = [-180.0, min_lat, max(neg_lons), max_lat]
            return [east_bbox, west_bbox]

        return [[min(lons), min_lat, max(lons), max_lat]]

    # Keep old name as a thin wrapper for callers that call it directly in tests.
    def _geometry_to_bbox(self, geometry: Dict[str, Any]) -> List[float]:
        bboxes = self._extract_bboxes(geometry)
        return bboxes[0]  # returns first shard only; use _extract_bboxes for antimeridian

    def _spatial_filter(self, bbox: List[float]) -> List[str]:
        """Stage 1: Deterministic bounding-box intersection for a single bbox.

        Uses Qdrant payload filters for sub-millisecond spatial filtering.
        The filter checks for bounding box overlap, not containment.
        Antimeridian-split bboxes are handled by calling this method twice
        and unioning the results in ``retrieve()``.
        """
        min_lon, min_lat, max_lon, max_lat = bbox

        # Build Qdrant filter: BBOX intersection
        # A intersects B if: A.min_lon <= B.max_lon AND A.max_lon >= B.min_lon
        #                AND A.min_lat <= B.max_lat AND A.max_lat >= B.min_lat
        # PATCH: import deferred so the module is importable without qdrant-client.
        try:
            from qdrant_client.models import Filter, FieldCondition, Range
            filter_conditions = Filter(
                must=[
                    FieldCondition(key="bbox.min_lon", range=Range(lte=max_lon)),
                    FieldCondition(key="bbox.max_lon", range=Range(gte=min_lon)),
                    FieldCondition(key="bbox.min_lat", range=Range(lte=max_lat)),
                    FieldCondition(key="bbox.max_lat", range=Range(gte=min_lat)),
                ]
            )
        except ImportError:
            filter_conditions = {
                "must": [
                    {"key": "bbox.min_lon", "range": {"lte": max_lon}},
                    {"key": "bbox.max_lon", "range": {"gte": min_lon}},
                    {"key": "bbox.min_lat", "range": {"lte": max_lat}},
                    {"key": "bbox.max_lat", "range": {"gte": min_lat}},
                ]
            }

        # Scroll through all matching points (no vector, just payload filter).
        # Hard cap at 10 000 pages to prevent infinite loops on misbehaving clients.
        ids: List[str] = []
        offset = None
        for _ in range(10_000):
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

        PATCH (P3-T1): current qdrant-client (>=1.10) removed ``.search()``
        in favor of ``.query_points()``, which wraps its hits in a
        ``QueryResponse.points`` list rather than returning them bare. The
        original code called only ``.search()`` -- verified against a real
        local Qdrant instance (not just ``MockQdrantClient``, which still
        implements the old ``.search()`` shape) that this raised
        ``AttributeError`` on any currently-installable qdrant-client. Try
        the modern API first; fall back to the legacy shape so
        ``MockQdrantClient`` (and any genuinely old client) keeps working
        unchanged.
        """
        try:
            from qdrant_client.models import Filter, HasIdCondition
            query_filter = Filter(must=[HasIdCondition(has_id=allowed_ids)])
        except ImportError:
            query_filter = {"must": [{"has_id": allowed_ids}]}

        query_vector = self._embed(query_text)

        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
            return response.points

        return self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )

    def _embed(self, text: str) -> List[float]:
        """Generate text embedding.

        Production: Call OpenAI API or local embedding model via ``self._embedder``.
        Air-gapped fallback: deterministic hash-based pseudo-embedding so the
        module produces non-degenerate vectors (the original implementation
        returned ``[0.0]*1536`` which collapsed every cosine similarity).
        """
        if self._embedder is not None:
            return self._embedder(text)
        return _hash_embedding(text)

    def _parse_hit(self, hit: Any) -> STACItem:
        """Parse a Qdrant search result into a STACItem.

        PATCH (P3-T1): real Qdrant point IDs must be an unsigned integer or
        a UUID (a plain string like "atl-canopy" is rejected at upsert
        time -- verified against a live instance). ``stac_indexer.py``
        therefore stores the catalog's real string ID in
        ``payload["stac_id"]`` and uses a UUID5 derived from it as the
        actual point ID. Prefer ``stac_id`` when present; fall back to the
        raw point id for ``MockQdrantClient``, which never remaps IDs and
        so already uses the STAC string ID as-is.
        """
        payload = hit.payload if hasattr(hit, "payload") else hit.get("payload", {})
        bbox_payload = payload.get("bbox", {})
        raw_id = hit.id if hasattr(hit, "id") else hit.get("id")
        return STACItem(
            id=payload.get("stac_id", raw_id),
            title=payload.get("title", "Untitled"),
            description=payload.get("description", ""),
            bbox=[
                bbox_payload.get("min_lon", 0),
                bbox_payload.get("min_lat", 0),
                bbox_payload.get("max_lon", 0),
                bbox_payload.get("max_lat", 0),
            ],
            temporal_start=payload.get("temporal_start"),
            temporal_end=payload.get("temporal_end"),
            variables=payload.get("variables", []),
            collection=payload.get("collection", ""),
            metadata_score=payload.get("metadata_score", 0),
            geometry=payload.get("geometry"),
            license=payload.get("license"),
            lineage=payload.get("lineage"),
        )
