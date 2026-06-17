"""DisasterRecoveryProcessor — routes DR events to backup/failover/replication
tables and a generic DR event log, feeding DR memory on failures."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from app.db.models import (
    Backup,
    DisasterRecoveryEvent,
    FailoverEvent,
    ReplicationStatus,
)
from app.memory.infrastructure_memory import get_memory
from app.processing.base import BaseProcessor, json_safe
from app.schemas.events import EventType, UnifiedEvent


class DisasterRecoveryProcessor(BaseProcessor):
    name = "disaster_recovery"

    def persist(self, event: UnifiedEvent, features: Dict[str, Any]):
        et = event.event_type
        if et == EventType.BACKUP.value:
            return self._persist_backup(event, features)
        if et == EventType.FAILOVER.value:
            return self._persist_failover(event, features)
        if et == EventType.REPLICATION.value:
            return self._persist_replication(event, features)
        return self._persist_dr_event(event, features)

    # --- specific persisters --- #
    def _persist_backup(self, event, f):
        row = Backup(
            system=f.get("system", event.service),
            service=event.service,
            status=f.get("status", "healthy"),
            last_backup=f.get("last_backup") or event.timestamp,
            rpo_minutes=int(f.get("rpo_minutes", 60) or 60),
            size_gb=float(f.get("size_gb", 0.0) or 0.0),
            meta=json_safe(f),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _persist_failover(self, event, f):
        row = FailoverEvent(
            service=event.service,
            region=f.get("region", ""),
            target_region=f.get("target_region", ""),
            status=f.get("status", "ready"),
            last_tested=f.get("last_tested"),
            rto_minutes=int(f.get("rto_minutes", 30) or 30),
            timestamp=event.timestamp,
            meta=json_safe(f),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _persist_replication(self, event, f):
        row = ReplicationStatus(
            source=f.get("source", event.service),
            target=f.get("target", ""),
            status=f.get("status", "in_sync"),
            lag_seconds=int(f.get("lag_seconds", 0) or 0),
            timestamp=event.timestamp,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _persist_dr_event(self, event, f):
        row = DisasterRecoveryEvent(
            event_type=f.get("event_type", "dr_event"),
            service=event.service,
            region=f.get("region", ""),
            status=f.get("status", ""),
            detail=f.get("detail", f.get("message", "")),
            timestamp=event.timestamp,
            meta=json_safe(f),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def embed(self, event: UnifiedEvent, persisted) -> None:
        if event.severity in {"high", "critical"}:
            get_memory().store_dr_incident(
                dr_id=f"{event.source}:{event.timestamp.isoformat()}",
                service=event.service,
                summary=f"{event.event_type} {event.metadata.get('status', '')}",
                outcome=event.metadata.get("detail", ""),
            )
