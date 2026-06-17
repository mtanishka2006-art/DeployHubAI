"""PagerDuty connector — pulls triggered/acknowledged incidents."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Tuple

import httpx

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent

_API = "https://api.pagerduty.com"


class PagerDutyConnector(BaseConnector):
    source = "pagerduty"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Token token={self.config['api_token']}",
            "Accept": "application/vnd.pagerduty+json;version=2",
        }

    def test_connection(self) -> Tuple[bool, str]:
        if not self._has("api_token"):
            return False, "api_token is required"
        try:
            r = httpx.get(
                f"{_API}/abilities", headers=self._headers(), timeout=10
            )
        except httpx.HTTPError as exc:
            return False, f"network error: {exc}"
        if r.status_code == 200:
            return True, "connected to PagerDuty"
        if r.status_code in (401, 403):
            return False, "invalid API token"
        return False, f"PagerDuty returned HTTP {r.status_code}"

    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        if not self._has("api_token"):
            return self.config.get("sample", [])
        try:
            r = httpx.get(
                f"{_API}/incidents",
                params={"statuses[]": ["triggered", "acknowledged"], "limit": 25},
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            incidents = r.json().get("incidents", [])
        except Exception as exc:  # noqa: BLE001
            self.log.warning("PagerDuty fetch failed: %s", exc)
            return []
        return [
            {
                "id": inc.get("id", ""),
                "title": inc.get("title", inc.get("summary", "")),
                "urgency": inc.get("urgency", "high"),
                "status": inc.get("status", "triggered"),
                "service": (inc.get("service") or {}).get("summary", "pagerduty"),
                "created_at": inc.get("created_at"),
            }
            for inc in incidents
        ]

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        severity = "critical" if raw.get("urgency") == "high" else "high"
        return UnifiedEvent(
            source=self.source,
            event_type=EventType.LOG.value,
            timestamp=raw.get("created_at") or datetime.now(timezone.utc),
            severity=severity,
            environment="prod",
            service=raw.get("service", "pagerduty"),
            metadata={
                "level": "error",
                "message": raw.get("title", "PagerDuty incident"),
                "error_signature": raw.get("title", "")[:60],
                "pd_status": raw.get("status", ""),
            },
        )
