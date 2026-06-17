"""Kubernetes connector — pod/node events and resource pressure metrics."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent

# Kubernetes event reasons that indicate trouble.
_BAD_REASONS = {
    "CrashLoopBackOff",
    "OOMKilled",
    "FailedScheduling",
    "BackOff",
    "Unhealthy",
    "NodeNotReady",
    "Evicted",
}


class KubernetesConnector(BaseConnector):
    source = "kubernetes"

    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        # Production: kubernetes client `list_event_for_all_namespaces` +
        # metrics-server. Config carries kubeconfig / in-cluster token.
        return self.config.get("sample", [])

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        kind = raw.get("kind", "event")
        if kind == "metric":
            return UnifiedEvent(
                source=self.source,
                event_type=EventType.METRIC.value,
                timestamp=raw.get("timestamp") or datetime.now(timezone.utc),
                severity=raw.get("severity", "info"),
                environment=raw.get("environment", "prod"),
                service=raw.get("service", raw.get("workload", "unknown")),
                metadata={
                    "metric_name": raw.get("metric_name", "pod_cpu"),
                    "value": raw.get("value", 0.0),
                    "unit": raw.get("unit", "cores"),
                    "namespace": raw.get("namespace", "default"),
                },
            )
        reason = raw.get("reason", "")
        severity = "critical" if reason in _BAD_REASONS else "info"
        return UnifiedEvent(
            source=self.source,
            event_type=EventType.LOG.value,
            timestamp=raw.get("timestamp") or datetime.now(timezone.utc),
            severity=severity,
            environment=raw.get("environment", "prod"),
            service=raw.get("workload", raw.get("service", "unknown")),
            metadata={
                "reason": reason,
                "message": raw.get("message", ""),
                "namespace": raw.get("namespace", "default"),
                "pod": raw.get("pod", ""),
                "level": "error" if severity == "critical" else "info",
            },
        )
