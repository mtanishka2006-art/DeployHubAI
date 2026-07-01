"""MetricProcessor — persists metric events as InfrastructureMetric rows."""
from __future__ import annotations

from typing import Any, Dict

from app.db.models import InfrastructureMetric
from app.processing.base import BaseProcessor, json_safe
from app.schemas.events import UnifiedEvent


class MetricProcessor(BaseProcessor):
    name = "metric"

    def extract_features(self, event: UnifiedEvent) -> Dict[str, Any]:
        md = dict(event.metadata)
        # Coerce numeric value defensively.
        try:
            md["value"] = float(md.get("value", 0.0))
        except (TypeError, ValueError):
            md["value"] = 0.0
        return md

    def persist(self, event: UnifiedEvent, features: Dict[str, Any]):
        metric = InfrastructureMetric(
            source=event.source,
            service=event.service,
            environment=event.environment,
            owner=features.get("_owner", ""),
            metric_name=features.get("metric_name", "metric"),
            value=features.get("value", 0.0),
            unit=features.get("unit", ""),
            timestamp=event.timestamp,
            meta=json_safe(
                {
                    k: v
                    for k, v in features.items()
                    if k not in {"value", "metric_name", "unit"}
                }
            ),
        )
        self.db.add(metric)
        self.db.flush()
        return metric
