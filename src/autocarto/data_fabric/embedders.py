"""Real embedding model adapter — Blueprint §6.2 P3-T4.

Wraps a local sentence-transformers model behind `HybridRetrieval`'s
existing `embedder: Callable[[str], list[float]]` injection point
(`hybrid_retrieval.py`, already present since the original review). This
module is purely additive: the deterministic `_hash_embedding` fallback
remains the tested, air-gap-safe default when no embedder is injected, and
nothing here changes that default.

Local, not an API call: after the one-time model download (~80 MB, cached
by huggingface_hub under ~/.cache), there is no network access or API key
at query time — this is the "local sentence-transformers" option the
Blueprint names as an alternative to OpenAI, chosen specifically because
it needs no key and keeps the retrieval layer's air-gap story intact for
everything except the initial download.
"""

from __future__ import annotations

from typing import List, Optional

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class SentenceTransformerEmbedder:
    """Real semantic embedder backed by a local sentence-transformers model.

    Default model (all-MiniLM-L6-v2, 384-dim, ~80 MB) is a speed/quality
    tradeoff appropriate for STAC metadata text — titles, descriptions,
    and variable names are short, not long-document retrieval, so a small
    model is not a meaningful quality compromise here.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "SentenceTransformerEmbedder requires the 'sentence-transformers' "
                "package: pip install sentence-transformers. The deterministic "
                "hash-embedding fallback remains available with no extra "
                "dependency via HybridRetrieval(embedder=None)."
            ) from exc
        self.model_name = model_name
        self._model = SentenceTransformer(model_name)

    @property
    def dimension(self) -> int:
        get_dim = getattr(self._model, "get_embedding_dimension", None)
        if get_dim is None:  # older sentence-transformers versions
            get_dim = self._model.get_sentence_embedding_dimension
        return int(get_dim())

    def __call__(self, text: str) -> List[float]:
        vector = self._model.encode(text, normalize_embeddings=True)
        return vector.tolist()
