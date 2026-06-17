"""Embedding provider.

Uses Sentence Transformers when available. If the model cannot be loaded
(offline, no download), falls back to a deterministic hashing embedder so the
RAG pipeline still functions end-to-end without network access.
"""
from __future__ import annotations

import hashlib
import math
from typing import List

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_DIM_FALLBACK = 384  # matches all-MiniLM-L6-v2 dimensionality


class EmbeddingProvider:
    def __init__(self) -> None:
        self._model = None
        self._dim = _DIM_FALLBACK
        self._load()

    def _load(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # lazy

            self._model = SentenceTransformer(settings.EMBEDDING_MODEL)
            self._dim = self._model.get_sentence_embedding_dimension()
            logger.info("Loaded embedding model %s (dim=%d)",
                        settings.EMBEDDING_MODEL, self._dim)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Sentence-Transformers unavailable (%s); using hashing embedder",
                exc,
            )
            self._model = None

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: List[str]) -> List[List[float]]:
        if self._model is not None:
            return self._model.encode(
                texts, normalize_embeddings=True
            ).tolist()
        return [self._hash_embed(t) for t in texts]

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]

    # ------------------------------------------------------------------ #
    # Deterministic fallback: bag-of-token hashing into a fixed vector,
    # L2-normalized. Good enough for cosine similarity on short incident text.
    # ------------------------------------------------------------------ #
    def _hash_embed(self, text: str) -> List[float]:
        vec = [0.0] * self._dim
        tokens = "".join(c.lower() if c.isalnum() else " " for c in text).split()
        for tok in tokens:
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            idx = h % self._dim
            sign = 1.0 if (h >> 8) & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    global _provider
    if _provider is None:
        _provider = EmbeddingProvider()
    return _provider
