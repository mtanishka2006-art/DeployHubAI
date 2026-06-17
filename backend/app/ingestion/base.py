"""Connector framework.

Every data source connector subclasses `BaseConnector`. The base class owns the
cross-cutting concerns — authentication, retry/backoff, normalization into the
Unified Event Schema, and publishing to Kafka — so each concrete connector only
implements `fetch_raw()` and `normalize()`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.logging import get_logger
from app.messaging.event_bus import EventBus, get_event_bus
from app.messaging.topics import EVENT_TYPE_TO_TOPIC, INCIDENT_EVENTS
from app.schemas.events import UnifiedEvent


class ConnectorError(Exception):
    """Raised when a connector cannot fetch or authenticate."""


class BaseConnector(ABC):
    """Abstract base for all ingestion connectors."""

    #: Stable source identifier used in the Unified Event Schema.
    source: str = "base"

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.config = config or {}
        self._bus = event_bus or get_event_bus()
        self.log = get_logger(f"connector.{self.source}")
        self._authenticated = False

    # ------------------------------------------------------------------ #
    # Lifecycle hooks — override as needed
    # ------------------------------------------------------------------ #
    def authenticate(self) -> None:
        """Establish credentials. Default is a no-op (token read from config)."""
        self._authenticated = True

    @abstractmethod
    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        """Pull raw records from the upstream system."""

    @abstractmethod
    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        """Convert one raw record into a UnifiedEvent."""

    # ------------------------------------------------------------------ #
    # Orchestration (provided by the base class)
    # ------------------------------------------------------------------ #
    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_exception_type(ConnectorError),
    )
    def _fetch_with_retry(self) -> List[Dict[str, Any]]:
        if not self._authenticated:
            self.authenticate()
        return list(self.fetch_raw())

    def collect(self) -> List[UnifiedEvent]:
        """Fetch + normalize without publishing (useful for tests/seeding)."""
        events: List[UnifiedEvent] = []
        for raw in self._fetch_with_retry():
            try:
                events.append(self.normalize(raw))
            except Exception:  # noqa: BLE001
                self.log.exception("normalization failed; skipping record")
        return events

    def run(self) -> int:
        """Full ingestion cycle: fetch -> normalize -> publish. Returns count."""
        events = self.collect()
        for event in events:
            topic = EVENT_TYPE_TO_TOPIC.get(event.event_type, INCIDENT_EVENTS)
            self._bus.publish(topic, event)
        self.log.info("published %d events", len(events))
        return len(events)
