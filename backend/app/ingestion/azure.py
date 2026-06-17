"""Azure connector — Azure Monitor metrics and Activity Log audit events."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent


class AzureConnector(BaseConnector):
    source = "azure"

    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        return self.config.get("sample", [])

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        stream = raw.get("stream", "monitor")
        if stream == "activity_log":
            return UnifiedEvent(
                source="azure_activity",
                event_type=EventType.AUDIT.value,
                timestamp=raw.get("timestamp") or datetime.now(timezone.utc),
                severity=raw.get("level", "info").lower(),
                environment=raw.get("environment", "prod"),
                service=raw.get("resource_provider", "azure"),
                metadata={
                    "operation": raw.get("operation_name"),
                    "caller": raw.get("caller"),
                    "region": raw.get("region", "eastus"),
                    "resource_group": raw.get("resource_group"),
                },
            )
        return UnifiedEvent(
            source="azure_monitor",
            event_type=EventType.METRIC.value,
            timestamp=raw.get("timestamp") or datetime.now(timezone.utc),
            severity=raw.get("severity", "info"),
            environment=raw.get("environment", "prod"),
            service=raw.get("service", "unknown"),
            metadata={
                "metric_name": raw.get("metric_name", "Percentage CPU"),
                "value": raw.get("value", 0.0),
                "unit": raw.get("unit", "Percent"),
                "region": raw.get("region", "eastus"),
            },
        )
