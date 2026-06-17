"""Jenkins CI connector — ingests build/deploy results."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent


class JenkinsConnector(BaseConnector):
    source = "jenkins"

    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        # In production this calls the Jenkins JSON API:
        #   GET {base_url}/job/{job}/api/json?tree=builds[...]
        # using an API token from self.config. Sample records keep the demo
        # self-contained.
        return self.config.get("sample", [])

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        result = (raw.get("result") or "SUCCESS").upper()
        status = {
            "SUCCESS": "success",
            "FAILURE": "failed",
            "ABORTED": "rolled_back",
        }.get(result, "in_progress")
        severity = "high" if status == "failed" else "info"
        return UnifiedEvent(
            source=self.source,
            event_type=EventType.DEPLOYMENT.value,
            timestamp=raw.get("timestamp") or datetime.now(timezone.utc),
            severity=severity,
            environment=raw.get("environment", "prod"),
            service=raw.get("job_name", "unknown"),
            metadata={
                "build_number": raw.get("number"),
                "status": status,
                "duration_seconds": int(raw.get("duration", 0)) // 1000
                if raw.get("duration")
                else raw.get("duration_seconds", 0),
                "actor": raw.get("actor", "jenkins"),
                "commit": raw.get("commit", ""),
                "version": raw.get("version", ""),
            },
        )
