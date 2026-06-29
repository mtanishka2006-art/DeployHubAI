"""DisasterRecoveryProcessor — routes DR events to backup/failover/replication
tables and a generic DR event log, feeding DR memory on failures."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import select

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
    # Backup / replication / failover are *state snapshots*, not an append-only
    # log: a connector re-reports the same entity every poll. Upsert by natural
    # key so repeated syncs update one row instead of accumulating duplicates.
    def _persist_backup(self, event, f):
        system = f.get("system", event.service)
        row = self.db.execute(
            select(Backup).where(Backup.system == system, Backup.service == event.service)
        ).scalar_one_or_none() or Backup(system=system, service=event.service)
        row.status = f.get("status", "healthy")
        row.last_backup = f.get("last_backup") or event.timestamp
        row.rpo_minutes = int(f.get("rpo_minutes", 60) or 60)
        row.size_gb = float(f.get("size_gb", 0.0) or 0.0)
        row.meta = json_safe(f)
        self.db.add(row)
        self.db.flush()
        return row

    def _persist_failover(self, event, f):
        region = f.get("region", "")
        row = self.db.execute(
            select(FailoverEvent).where(
                FailoverEvent.service == event.service, FailoverEvent.region == region
            )
        ).scalar_one_or_none() or FailoverEvent(service=event.service, region=region)
        row.target_region = f.get("target_region", "")
        row.status = f.get("status", "ready")
        row.last_tested = f.get("last_tested")
        row.rto_minutes = int(f.get("rto_minutes", 30) or 30)
        row.timestamp = event.timestamp
        row.meta = json_safe(f)
        self.db.add(row)
        self.db.flush()
        return row

    def _persist_replication(self, event, f):
        src = f.get("source", event.service)
        target = f.get("target", "")
        row = self.db.execute(
            select(ReplicationStatus).where(
                ReplicationStatus.source == src, ReplicationStatus.target == target
            )
        ).scalar_one_or_none() or ReplicationStatus(source=src, target=target)
        row.status = f.get("status", "in_sync")
        row.lag_seconds = int(f.get("lag_seconds", 0) or 0)
        row.timestamp = event.timestamp
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
