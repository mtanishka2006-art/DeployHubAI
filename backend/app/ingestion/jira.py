"""Jira connector — imports incident/outage-labelled issues as incidents."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Tuple

import httpx

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent

_JQL = 'labels in (incident, outage) ORDER BY created DESC'


class JiraConnector(BaseConnector):
    source = "jira"

    def _auth(self):
        return (self.config["email"], self.config["api_token"])

    def _base(self) -> str:
        domain = self.config["domain"].replace("https://", "").rstrip("/")
        return f"https://{domain}/rest/api/3"

    def test_connection(self) -> Tuple[bool, str]:
        if not self._has("domain", "email", "api_token"):
            return False, "domain, email and api_token are required"
        try:
            r = httpx.get(f"{self._base()}/myself", auth=self._auth(), timeout=10)
        except httpx.HTTPError as exc:
            return False, f"network error: {exc}"
        if r.status_code == 200:
            return True, "connected to Jira"
        if r.status_code in (401, 403):
            return False, "invalid email or API token"
        return False, f"Jira returned HTTP {r.status_code}"

    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        if not self._has("domain", "email", "api_token"):
            return self.config.get("sample", [])
        try:
            r = httpx.get(
                f"{self._base()}/search",
                params={"jql": _JQL, "maxResults": 25,
                        "fields": "summary,status,priority,created,project"},
                auth=self._auth(),
                timeout=15,
            )
            r.raise_for_status()
            issues = r.json().get("issues", [])
        except Exception as exc:  # noqa: BLE001
            self.log.warning("Jira fetch failed: %s", exc)
            return []
        out = []
        for issue in issues:
            f = issue.get("fields", {})
            priority = (f.get("priority") or {}).get("name", "Medium")
            out.append(
                {
                    "key": issue.get("key", ""),
                    "summary": f.get("summary", ""),
                    "priority": priority,
                    "created": f.get("created"),
                    "project": (f.get("project") or {}).get("key", "jira"),
                    "status": (f.get("status") or {}).get("name", ""),
                }
            )
        return out

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        priority = (raw.get("priority") or "Medium").lower()
        severity = {
            "highest": "critical", "high": "high",
            "medium": "medium", "low": "low", "lowest": "info",
        }.get(priority, "high")
        return UnifiedEvent(
            source=self.source,
            event_type=EventType.LOG.value,  # high/critical -> Incident
            timestamp=raw.get("created") or datetime.now(timezone.utc),
            severity=severity if severity in {"high", "critical"} else "high",
            environment="prod",
            service=raw.get("project", "jira"),
            metadata={
                "level": "error",
                "message": f"[{raw.get('key', '')}] {raw.get('summary', '')}",
                "error_signature": raw.get("summary", "")[:60],
                "jira_status": raw.get("status", ""),
            },
        )
