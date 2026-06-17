"""The Unified Event Schema.

Every connector normalizes upstream data into this single envelope before it is
published to Kafka and consumed by the processing layer. Keeping one schema
across 13 heterogeneous sources is what makes the rest of the pipeline generic.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any, Dict

from pydantic import BaseModel, Field


class EventType(str, enum.Enum):
    METRIC = "metric"
    LOG = "log"
    DEPLOYMENT = "deployment"
    INCIDENT = "incident"
    DR_EVENT = "dr_event"
    BACKUP = "backup"
    FAILOVER = "failover"
    REPLICATION = "replication"
    AUDIT = "audit"


class UnifiedEvent(BaseModel):
    """Normalized event envelope (matches the platform's canonical contract)."""

    source: str = Field(..., description="Originating system, e.g. 'jenkins'")
    event_type: str = Field(..., description="Logical event class")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    severity: str = Field(default="info")
    environment: str = Field(default="prod")
    service: str = Field(default="unknown")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def key(self) -> str:
        """Partition key for Kafka — groups a service's events together."""
        return f"{self.source}:{self.service}"
