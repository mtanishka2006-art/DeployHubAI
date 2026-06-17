"""Datadog connector — ingests events and alerting monitors.

Monitors in an Alert state become incidents; events become metric/log signal.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

import httpx

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent


class DatadogConnector(BaseConnector):
    source = "datadog"

    def _base(self) -> str:
        site = self.config.get("site") or "datadoghq.com"
        return f"https://api.{site}"

    def _headers(self) -> Dict[str, str]:
        return {
            "DD-API-KEY": self.config["api_key"],
            "DD-APPLICATION-KEY": self.config["app_key"],
        }

    def test_connection(self) -> Tuple[bool, str]:
        if not self._has("api_key", "app_key"):
            return False, "api_key and app_key are required"
        try:
            r = httpx.get(
                f"{self._base()}/api/v1/validate",
                headers=self._headers(),
                timeout=10,
            )
        except httpx.HTTPError as exc:
            return False, f"network error: {exc}"
        if r.status_code == 200:
            return True, "connected to Datadog"
        if r.status_code in (401, 403):
            return False, "invalid API/application key"
        return False, f"Datadog returned HTTP {r.status_code}"

    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        if not self._has("api_key", "app_key"):
            return self.config.get("sample", [])
        records: List[Dict[str, Any]] = []
        # Alerting monitors -> incidents
        try:
            r = httpx.get(
                f"{self._base()}/api/v1/monitor",
                params={"group_states": "alert"},
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            for m in r.json():
                state = (m.get("overall_state") or "").lower()
                if state in ("alert", "warn"):
                    records.append(
                        {
                            "kind": "monitor",
                            "name": m.get("name", "Datadog monitor"),
                            "state": state,
                            "service": (m.get("tags") or ["datadog"])[0]
                            if m.get("tags") else "datadog",
                            "message": m.get("message", ""),
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            self.log.warning("Datadog monitor fetch failed: %s", exc)
        return records

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        if raw.get("kind") == "monitor":
            severity = "critical" if raw.get("state") == "alert" else "high"
            return UnifiedEvent(
                source=self.source,
                event_type=EventType.LOG.value,
                timestamp=datetime.now(timezone.utc),
                severity=severity,
                environment="prod",
                service=str(raw.get("service", "datadog")).replace("service:", ""),
                metadata={
                    "level": "error",
                    "message": raw.get("name", "Datadog monitor alert"),
                    "error_signature": str(raw.get("name", ""))[:60],
                },
            )
        # Generic metric/event
        return UnifiedEvent(
            source=self.source,
            event_type=EventType.METRIC.value,
            timestamp=datetime.now(timezone.utc),
            severity=raw.get("severity", "info"),
            environment="prod",
            service=str(raw.get("service", "datadog")),
            metadata={
                "metric_name": raw.get("metric_name", "datadog_event"),
                "value": raw.get("value", 1.0),
                "unit": raw.get("unit", "count"),
            },
        )
