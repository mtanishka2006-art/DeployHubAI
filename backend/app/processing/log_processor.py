"""LogProcessor — turns error/critical logs into incidents and feeds memory.

Info/low logs are summarized as lightweight metrics (log volume) rather than
stored verbatim, keeping the store focused on signal.
"""
from __future__ import annotations

from typing import Any, Dict

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
        md["error_signature"] = self._signature(msg)
        md["is_error"] = event.severity in _INCIDENT_SEVERITIES
        return md

    def persist(self, event: UnifiedEvent, features: Dict[str, Any]):
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

        incident = Incident(
            title=f"{event.service}: {features.get('error_signature', 'error')}",
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
