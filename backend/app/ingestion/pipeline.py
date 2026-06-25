"""Shared ingestion pipeline: route UnifiedEvents to the right processor.

The in-memory event bus has no DB subscriber, so the seeding scripts, the manual
sync endpoint, and the background poller all funnel events into the database
through this single helper — keeping the persistence logic in one place.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.models import ConnectedApp, ConnectorEvent
from app.processing.deployment_processor import DeploymentProcessor
from app.processing.dr_processor import DisasterRecoveryProcessor
from app.processing.log_processor import LogProcessor
from app.processing.metric_processor import MetricProcessor
from app.schemas.events import EventType, UnifiedEvent

logger = get_logger("ingestion.pipeline")

_DR_EVENT_TYPES = {
    EventType.DR_EVENT.value,
    EventType.BACKUP.value,
    EventType.FAILOVER.value,
    EventType.REPLICATION.value,
}


def _processor_for(event_type: str, db: Session):
    if event_type == EventType.METRIC.value:
        return MetricProcessor(db)
    if event_type == EventType.LOG.value:
        return LogProcessor(db)
    if event_type == EventType.DEPLOYMENT.value:
        return DeploymentProcessor(db)
    if event_type == EventType.AUDIT.value:
        # Audit events are tracked as metric/log signal.
        return MetricProcessor(db)
    if event_type in _DR_EVENT_TYPES:
        return DisasterRecoveryProcessor(db)
    return LogProcessor(db)


def _summarize(event: UnifiedEvent) -> str:
    md = event.metadata or {}
    return (
        md.get("message")
        or md.get("title")
        or md.get("summary")
        or md.get("status")
        or f"{event.event_type} on {event.service}"
    )


def ingest_events(
    db: Session,
    events: List[UnifiedEvent],
    connected_app: Optional[ConnectedApp] = None,
) -> int:
    """Persist a batch of events through the processors. When a ConnectedApp is
    given, also logs a ConnectorEvent per event and updates the app's counters.
    Returns the number of events successfully ingested."""
    count = 0
    for event in events:
        try:
            processor = _processor_for(event.event_type, db)
            processor.process(event)
            # Recovery markers (metadata.resolve) are internal signals that
            # close incidents — don't record them in the connector/log feed.
            if connected_app is not None and not (event.metadata or {}).get("resolve"):
                db.add(
                    ConnectorEvent(
                        connected_app_id=connected_app.id,
                        app_type=connected_app.app_type,
                        source=event.source,
                        event_type=event.event_type,
                        service=event.service,
                        severity=event.severity,
                        summary=str(_summarize(event))[:500],
                        timestamp=event.timestamp,
                    )
                )
            count += 1
        except Exception:  # noqa: BLE001 - never let one bad event break the batch
            logger.exception("failed to ingest event from %s", event.source)

    if connected_app is not None:
        connected_app.events_ingested = (connected_app.events_ingested or 0) + count
        connected_app.last_synced_at = utcnow()
    db.commit()
    return count
