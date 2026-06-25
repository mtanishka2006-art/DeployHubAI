"""LogProcessor — turns error/critical logs into incidents and feeds memory.

Info/low logs are summarized as lightweight metrics (log volume) rather than
stored verbatim, keeping the store focused on signal.
"""
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import select

from app.db.models import Incident, InfrastructureMetric, Severity
from app.memory.infrastructure_memory import get_memory
from app.processing.base import BaseProcessor, json_safe
from app.schemas.events import UnifiedEvent

_INCIDENT_SEVERITIES = {Severity.HIGH.value, Severity.CRITICAL.value}


class LogProcessor(BaseProcessor):
    name = "log"

    def extract_features(self, event: UnifiedEvent) -> Dict[str, Any]:
        md = dict(event.metadata)
        msg = md.get("message", "")
        # Respect a connector-supplied (stable) signature; else derive one. A
        # stable signature lets recurring alerts de-duplicate instead of piling
        # up a new incident every poll.
        if not md.get("error_signature"):
            md["error_signature"] = self._signature(msg)
        md["is_error"] = event.severity in _INCIDENT_SEVERITIES
        return md

    def persist(self, event: UnifiedEvent, features: Dict[str, Any]):
        # Recovery signal: a connector reports a check is healthy again. Close
        # the matching OPEN incident instead of creating anything. This only
        # fires when the connector genuinely observed the issue clear.
        if features.get("resolve"):
            return self._resolve_incident(event, features)

        if not features.get("is_error"):
            # Track log volume as a metric for the monitoring agent.
            metric = InfrastructureMetric(
                source=event.source,
                service=event.service,
                environment=event.environment,
                metric_name="log_event",
                value=1.0,
                unit="count",
                timestamp=event.timestamp,
                meta={"level": features.get("level", "info")},
            )
            self.db.add(metric)
            self.db.flush()
            return metric

        title = f"{event.service}: {features.get('error_signature', 'error')}"

        # De-duplicate: if the same issue is already an open incident on this
        # service, don't create another one each poll — keep the existing one.
        existing = self.db.execute(
            select(Incident)
            .where(
                Incident.service == event.service,
                Incident.title == title,
                Incident.status.in_(["open", "investigating"]),
            )
            .limit(1)
        ).scalars().first()
        if existing is not None:
            return existing

        incident = Incident(
            title=title,
            description=features.get("message", ""),
            severity=event.severity,
            service=event.service,
            environment=event.environment,
            source=event.source,
            detected_at=event.timestamp,
            meta=json_safe({k: v for k, v in features.items() if k != "message"}),
        )
        self.db.add(incident)
        self.db.flush()
        return incident

    def _resolve_incident(self, event: UnifiedEvent, features: Dict[str, Any]):
        """Close the open incident matching this service + signature, if any."""
        title = f"{event.service}: {features.get('error_signature', 'error')}"
        inc = self.db.execute(
            select(Incident)
            .where(
                Incident.service == event.service,
                Incident.title == title,
                Incident.status.in_(["open", "investigating"]),
            )
            .limit(1)
        ).scalars().first()
        if inc is not None:
            inc.status = "resolved"
            inc.resolved_at = event.timestamp
            self.db.flush()
        return inc

    def embed(self, event: UnifiedEvent, persisted) -> None:
        if isinstance(persisted, Incident):
            get_memory().store_incident(
                incident_id=str(persisted.id),
                title=persisted.title,
                summary=persisted.description,
                service=persisted.service,
                severity=persisted.severity,
                occurred_at=persisted.detected_at.isoformat(),
            )

    @staticmethod
    def _signature(message: str) -> str:
        """A coarse error signature: first 8 words, exceptions emphasized."""
        if not message:
            return "error"
        for token in message.split():
            if token.endswith("Error") or token.endswith("Exception"):
                return token
        return " ".join(message.split()[:8])
