"""Infrastructure Memory — the enterprise RAG layer.

Wraps the vector store with domain-specific operations that let AI agents learn
from historical incidents and recoveries. Public API matches the platform spec:

    store_incident()
    store_resolution()
    search_similar_incidents()
    retrieve_recovery_history()
    build_context()
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.memory.vector_store import get_vector_store

logger = get_logger(__name__)


class InfrastructureMemory:
    def __init__(self) -> None:
        self._store = get_vector_store()

    # ------------------------------------------------------------------ #
    # Write paths
    # ------------------------------------------------------------------ #
    def store_incident(
        self,
        incident_id: str,
        title: str,
        summary: str,
        root_cause: str = "",
        service: str = "",
        severity: str = "medium",
        occurred_at: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        document = self._incident_document(title, summary, root_cause, service)
        self._store.add(
            "incident_memory",
            ids=[f"incident:{incident_id}"],
            documents=[document],
            metadatas=[
                {
                    "kind": "incident",
                    "title": title,
                    "summary": summary,
                    "root_cause": root_cause,
                    "service": service,
                    "severity": severity,
                    "occurred_at": occurred_at or "",
                    "tags": ",".join(tags or []),
                }
            ],
        )

    def store_resolution(
        self,
        incident_id: str,
        recovery_actions: List[str],
        outcome: str,
        title: str = "",
        root_cause: str = "",
        service: str = "",
    ) -> None:
        doc = (
            f"Resolution for {title or incident_id}. Root cause: {root_cause}. "
            f"Actions: {'; '.join(recovery_actions)}. Outcome: {outcome}"
        )
        self._store.add(
            "recovery_memory",
            ids=[f"resolution:{incident_id}"],
            documents=[doc],
            metadatas=[
                {
                    "kind": "resolution",
                    "incident_id": str(incident_id),
                    "title": title,
                    "root_cause": root_cause,
                    "service": service,
                    "recovery_actions": " | ".join(recovery_actions),
                    "outcome": outcome,
                }
            ],
        )

    def store_deployment_failure(
        self, deployment_id: str, service: str, summary: str, root_cause: str = ""
    ) -> None:
        self._store.add(
            "deployment_memory",
            ids=[f"deploy:{deployment_id}"],
            documents=[f"Deployment failure in {service}: {summary}. {root_cause}"],
            metadatas=[
                {
                    "kind": "deployment_failure",
                    "title": f"{service}: {summary}",
                    "service": service,
                    "summary": summary,
                    "root_cause": root_cause,
                }
            ],
        )

    def store_dr_incident(
        self, dr_id: str, service: str, summary: str, outcome: str = ""
    ) -> None:
        self._store.add(
            "dr_memory",
            ids=[f"dr:{dr_id}"],
            documents=[f"DR incident for {service}: {summary}. Outcome: {outcome}"],
            metadatas=[
                {
                    "kind": "dr_incident",
                    "title": f"{service}: {summary}",
                    "service": service,
                    "summary": summary,
                    "outcome": outcome,
                }
            ],
        )

    # ------------------------------------------------------------------ #
    # Read paths
    # ------------------------------------------------------------------ #
    def search_similar_incidents(
        self, query: str, k: int = 5, collection: str = "incident_memory"
    ) -> List[Dict[str, Any]]:
        rows = self._store.query(collection, query, k=k)
        results = []
        for r in rows:
            meta = r.get("metadata", {})
            results.append(
                {
                    "id": r["id"],
                    "title": meta.get("title", ""),
                    "summary": meta.get("summary", r.get("document", "")),
                    "root_cause": meta.get("root_cause", ""),
                    "recovery_actions": _split(meta.get("recovery_actions", "")),
                    "outcome": meta.get("outcome", ""),
                    "score": r.get("score", 0.0),
                    "occurred_at": meta.get("occurred_at", ""),
                }
            )
        return results

    def retrieve_recovery_history(
        self, query: str, k: int = 5
    ) -> List[Dict[str, Any]]:
        return self.search_similar_incidents(query, k=k, collection="recovery_memory")

    def build_context(self, query: str, k: int = 4) -> str:
        """Assemble a compact textual context block for an LLM/agent prompt."""
        incidents = self.search_similar_incidents(query, k=k)
        recoveries = self.retrieve_recovery_history(query, k=k)
        lines: List[str] = []
        if incidents:
            lines.append("## Similar past incidents")
            for i, inc in enumerate(incidents, 1):
                lines.append(
                    f"{i}. [{inc['score']:.2f}] {inc['title']} — "
                    f"root cause: {inc['root_cause'] or 'unknown'}"
                )
        if recoveries:
            lines.append("\n## Recovery history")
            for i, rec in enumerate(recoveries, 1):
                actions = ", ".join(rec["recovery_actions"][:3]) or rec["summary"]
                lines.append(f"{i}. [{rec['score']:.2f}] {actions} -> {rec['outcome']}")
        return "\n".join(lines) if lines else "No relevant history found."

    def stats(self) -> Dict[str, int]:
        from app.memory.vector_store import COLLECTIONS

        return {c: self._store.count(c) for c in COLLECTIONS}

    @staticmethod
    def _incident_document(
        title: str, summary: str, root_cause: str, service: str
    ) -> str:
        return (
            f"Service: {service}. Incident: {title}. {summary} "
            f"Root cause: {root_cause}"
        )


def _split(value: str) -> List[str]:
    if not value:
        return []
    for sep in (" | ", ";", ","):
        if sep in value:
            return [p.strip() for p in value.split(sep) if p.strip()]
    return [value.strip()]


_memory: Optional[InfrastructureMemory] = None


def get_memory() -> InfrastructureMemory:
    global _memory
    if _memory is None:
        _memory = InfrastructureMemory()
    return _memory
