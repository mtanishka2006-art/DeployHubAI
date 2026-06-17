"""Base processor.

Processors transform UnifiedEvents into persisted domain rows. The base class
provides the shared pipeline (clean -> extract features -> enrich -> persist ->
embed -> republish) and concrete processors override the hooks they need.
"""
from __future__ import annotations

import datetime as _dt
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.messaging.event_bus import EventBus, get_event_bus
from app.schemas.events import UnifiedEvent


def json_safe(value: Any) -> Any:
    """Recursively coerce a value into something JSON-serializable.

    Connectors may carry native datetime objects (e.g. boto3 / k8s clients) in
    event metadata; the JSON columns need ISO strings, not datetimes.
    """
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    return value


class BaseProcessor(ABC):
    name: str = "base"

    def __init__(self, db: Session, event_bus: Optional[EventBus] = None) -> None:
        self.db = db
        self._bus = event_bus or get_event_bus()
        self.log = get_logger(f"processor.{self.name}")

    # ---- hooks ---- #
    def clean(self, event: UnifiedEvent) -> UnifiedEvent:
        """Normalize/sanitize fields. Default trims service + lowercases sev."""
        event.service = (event.service or "unknown").strip().lower()
        event.severity = (event.severity or "info").strip().lower()
        return event

    def extract_features(self, event: UnifiedEvent) -> Dict[str, Any]:
        """Derive features used downstream. Default: passthrough metadata."""
        return dict(event.metadata)

    def enrich(self, event: UnifiedEvent, features: Dict[str, Any]) -> Dict[str, Any]:
        """Add derived context (env tags, computed flags)."""
        features["_environment"] = event.environment
        features["_source"] = event.source
        return features

    @abstractmethod
    def persist(self, event: UnifiedEvent, features: Dict[str, Any]) -> Any:
        """Write the domain row(s). Return the persisted object."""

    def embed(self, event: UnifiedEvent, persisted: Any) -> None:
        """Optionally push to vector memory. Default no-op."""

    # ---- pipeline ---- #
    def process(self, event: UnifiedEvent) -> Any:
        event = self.clean(event)
        features = self.enrich(event, self.extract_features(event))
        obj = self.persist(event, features)
        try:
            self.embed(event, obj)
        except Exception:  # noqa: BLE001
            self.log.exception("embedding failed (non-fatal)")
        return obj

    def process_batch(self, events: List[UnifiedEvent]) -> int:
        count = 0
        for ev in events:
            try:
                self.process(ev)
                count += 1
            except Exception:  # noqa: BLE001
                self.log.exception("failed to process event from %s", ev.source)
        self.db.commit()
        return count
