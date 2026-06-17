"""Vector store abstraction over ChromaDB with an in-memory fallback.

Collections:
    incident_memory, deployment_memory, recovery_memory, dr_memory
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.config import settings
from app.core.logging import get_logger
from app.memory.embeddings import get_embedding_provider

logger = get_logger(__name__)

COLLECTIONS = [
    "incident_memory",
    "deployment_memory",
    "recovery_memory",
    "dr_memory",
]


class VectorStore(ABC):
    @abstractmethod
    def add(
        self,
        collection: str,
        ids: List[str],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None: ...

    @abstractmethod
    def query(
        self, collection: str, text: str, k: int = 5
    ) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def count(self, collection: str) -> int: ...

    @abstractmethod
    def reset(self) -> None:
        """Drop all stored vectors across every collection."""


class ChromaVectorStore(VectorStore):
    def __init__(self) -> None:
        import chromadb  # lazy

        if settings.CHROMA_HOST:
            self._client = chromadb.HttpClient(
                host=settings.CHROMA_HOST, port=settings.CHROMA_PORT
            )
        else:
            self._client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        self._embed = get_embedding_provider()
        self._cols = {
            name: self._client.get_or_create_collection(
                name, metadata={"hnsw:space": "cosine"}
            )
            for name in COLLECTIONS
        }
        logger.info("ChromaVectorStore ready (%d collections)", len(self._cols))

    def add(self, collection, ids, documents, metadatas) -> None:
        col = self._cols[collection]
        embeddings = self._embed.embed(documents)
        col.upsert(
            ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings
        )

    def query(self, collection, text, k=5) -> List[Dict[str, Any]]:
        col = self._cols[collection]
        if col.count() == 0:
            return []
        emb = self._embed.embed_one(text)
        res = col.query(query_embeddings=[emb], n_results=min(k, col.count()))
        out: List[Dict[str, Any]] = []
        for i in range(len(res["ids"][0])):
            dist = res["distances"][0][i] if res.get("distances") else 0.0
            out.append(
                {
                    "id": res["ids"][0][i],
                    "document": res["documents"][0][i],
                    "metadata": res["metadatas"][0][i],
                    "score": round(1.0 - dist, 4),  # cosine distance -> similarity
                }
            )
        return out

    def count(self, collection) -> int:
        return self._cols[collection].count()

    def reset(self) -> None:
        for name in list(self._cols):
            try:
                self._client.delete_collection(name)
            except Exception:  # noqa: BLE001
                pass
            self._cols[name] = self._client.get_or_create_collection(
                name, metadata={"hnsw:space": "cosine"}
            )


class InMemoryVectorStore(VectorStore):
    """Cosine-similarity store backed by the embedding provider. Keeps the RAG
    pipeline fully functional with no external vector DB."""

    def __init__(self) -> None:
        self._embed = get_embedding_provider()
        self._data: Dict[str, List[Dict[str, Any]]] = {c: [] for c in COLLECTIONS}

    def add(self, collection, ids, documents, metadatas) -> None:
        store = self._data.setdefault(collection, [])
        embeddings = self._embed.embed(documents)
        existing = {row["id"]: row for row in store}
        for _id, doc, meta, emb in zip(ids, documents, metadatas, embeddings):
            row = {"id": _id, "document": doc, "metadata": meta, "embedding": emb}
            existing[_id] = row
        self._data[collection] = list(existing.values())

    def query(self, collection, text, k=5) -> List[Dict[str, Any]]:
        store = self._data.get(collection, [])
        if not store:
            return []
        q = self._embed.embed_one(text)
        scored = [
            {**row, "score": round(self._cosine(q, row["embedding"]), 4)}
            for row in store
        ]
        scored.sort(key=lambda r: r["score"], reverse=True)
        return [
            {k2: v for k2, v in r.items() if k2 != "embedding"}
            for r in scored[:k]
        ]

    def count(self, collection) -> int:
        return len(self._data.get(collection, []))

    def reset(self) -> None:
        self._data = {c: [] for c in COLLECTIONS}

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (na * nb)


_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is not None:
        return _store
    try:
        _store = ChromaVectorStore()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ChromaDB unavailable (%s); using in-memory vector store", exc)
        _store = InMemoryVectorStore()
    return _store
