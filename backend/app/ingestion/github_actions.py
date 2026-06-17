"""GitHub Actions connector — ingests workflow run results."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent


class GithubActionsConnector(BaseConnector):
    source = "github_actions"

    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        # Production: GET /repos/{owner}/{repo}/actions/runs with a PAT.
        return self.config.get("sample", [])

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        conclusion = (raw.get("conclusion") or "success").lower()
        status = {
            "success": "success",
            "failure": "failed",
            "cancelled": "rolled_back",
        }.get(conclusion, "in_progress")
        return UnifiedEvent(
            source=self.source,
            event_type=EventType.DEPLOYMENT.value,
            timestamp=raw.get("created_at") or datetime.now(timezone.utc),
            severity="high" if status == "failed" else "info",
            environment=raw.get("environment", "prod"),
            service=raw.get("repository", raw.get("workflow", "unknown")),
            metadata={
                "status": status,
                "actor": raw.get("actor", ""),
                "commit": raw.get("head_sha", "")[:12],
                "version": raw.get("run_number", ""),
                "duration_seconds": raw.get("duration_seconds", 0),
            },
        )
