"""Log connector — application and infrastructure log lines."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent

_LEVEL_SEVERITY = {
    "TRACE": "info",
    "DEBUG": "info",
    "INFO": "info",
    "WARN": "low",
    "WARNING": "low",
    "ERROR": "high",
    "FATAL": "critical",
    "CRITICAL": "critical",
}

# Loose pattern: "<ts> <LEVEL> <service>: <message>"
_LINE_RE = re.compile(
    r"^(?P<ts>\S+)\s+(?P<level>[A-Z]+)\s+(?P<service>[\w\-.]+):?\s*(?P<msg>.*)$"
)


class LogConnector(BaseConnector):
    """Handles both application logs and infrastructure logs. The
    ``log_type`` config value (``application`` | ``infrastructure``) is recorded
    in metadata so downstream processors can distinguish them."""

    source = "logs"

    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        return self.config.get("sample", [])

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        # Accept both structured dicts and raw log lines.
        if isinstance(raw.get("line"), str) and "level" not in raw:
            parsed = self._parse_line(raw["line"])
            raw = {**parsed, **{k: v for k, v in raw.items() if k != "line"}}
        level = (raw.get("level") or "INFO").upper()
        return UnifiedEvent(
            source=self.source,
            event_type=EventType.LOG.value,
            timestamp=raw.get("timestamp") or datetime.now(timezone.utc),
            severity=_LEVEL_SEVERITY.get(level, "info"),
            environment=raw.get("environment", "prod"),
            service=raw.get("service", "unknown"),
            metadata={
                "level": level.lower(),
                "message": raw.get("message", ""),
                "log_type": self.config.get("log_type", "application"),
                "host": raw.get("host", ""),
            },
        )

    @staticmethod
    def _parse_line(line: str) -> Dict[str, Any]:
        m = _LINE_RE.match(line.strip())
        if not m:
            return {"level": "INFO", "message": line, "service": "unknown"}
        return {
            "level": m.group("level"),
            "service": m.group("service"),
            "message": m.group("msg"),
        }
