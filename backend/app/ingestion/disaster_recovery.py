"""Disaster Recovery connector.

Unifies four DR-adjacent sources: backup systems, replication systems,
failover monitoring, and generic DR system events. The raw ``dr_type`` field
selects which it is.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent

_DR_TYPE_TO_EVENT = {
    "backup": EventType.BACKUP.value,
    "replication": EventType.REPLICATION.value,
    "failover": EventType.FAILOVER.value,
    "dr_event": EventType.DR_EVENT.value,
}


class DisasterRecoveryConnector(BaseConnector):
    source = "disaster_recovery"

    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        return self.config.get("sample", [])

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        dr_type = raw.get("dr_type", "dr_event")
        event_type = _DR_TYPE_TO_EVENT.get(dr_type, EventType.DR_EVENT.value)
        status = raw.get("status", "healthy")
        severity = self._severity_for(dr_type, status, raw)
        return UnifiedEvent(
            source=self.source,
            event_type=event_type,
            timestamp=raw.get("timestamp") or datetime.now(timezone.utc),
            severity=severity,
            environment=raw.get("environment", "prod"),
            service=raw.get("service", raw.get("system", "unknown")),
            metadata={k: v for k, v in raw.items() if k != "timestamp"},
        )

    @staticmethod
    def _severity_for(dr_type: str, status: str, raw: Dict[str, Any]) -> str:
        if status in {"failed", "stale", "out_of_sync", "degraded"}:
            return "critical"
        if dr_type == "replication" and int(raw.get("lag_seconds", 0)) > 300:
            return "high"
        if dr_type == "backup" and int(raw.get("rpo_minutes", 0)) > 240:
            return "medium"
        return "info"
