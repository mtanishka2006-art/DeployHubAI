"""GitHub Actions connector — ingests workflow run results.

Live mode (when owner/repo/token are supplied) calls the GitHub REST API; with
no credentials it falls back to ``config['sample']`` so seeding/tests still work.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Tuple

import httpx

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent

_API = "https://api.github.com"


def _headers(token: str = "") -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    # Token is only needed for private repos / higher rate limits. Public repos
    # work unauthenticated, so only send Authorization when a token is given.
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


class GithubActionsConnector(BaseConnector):
    source = "github_actions"

    def test_connection(self) -> Tuple[bool, str]:
        if not self._has("owner", "repo"):
            return False, "owner and repo are required"
        owner, repo = self.config["owner"], self.config["repo"]
        token = self.config.get("token", "")
        try:
            r = httpx.get(
                f"{_API}/repos/{owner}/{repo}",
                headers=_headers(token),
                timeout=10,
            )
        except httpx.HTTPError as exc:
            return False, f"network error: {exc}"
        if r.status_code == 200:
            suffix = "" if token else " (public, no token)"
            return True, f"connected to {owner}/{repo}{suffix}"
        if r.status_code == 404:
            return False, "repository not found (private repos need an access token)"
        if r.status_code in (401, 403):
            return False, (
                "this repo needs a valid access token "
                "(private repo, or public rate limit hit)"
            )
        return False, f"GitHub returned HTTP {r.status_code}"

    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        if not self._has("owner", "repo"):
            return self.config.get("sample", [])
        owner, repo = self.config["owner"], self.config["repo"]
        token = self.config.get("token", "")
        url = f"{_API}/repos/{owner}/{repo}/actions/runs?per_page=20"
        try:
            r = httpx.get(url, headers=_headers(token), timeout=15)
            r.raise_for_status()
            runs = r.json().get("workflow_runs", [])
        except Exception as exc:  # noqa: BLE001
            self.log.warning("GitHub fetch failed: %s", exc)
            return []
        return [
            {
                "repository": repo,
                "workflow": run.get("name"),
                "conclusion": run.get("conclusion") or "in_progress",
                "actor": (run.get("actor") or {}).get("login", ""),
                "head_sha": run.get("head_sha", ""),
                "run_number": str(run.get("run_number", "")),
                "created_at": run.get("run_started_at") or run.get("created_at"),
                "environment": "prod",
            }
            for run in runs
        ]

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
                "commit": (raw.get("head_sha", "") or "")[:12],
                "version": raw.get("run_number", ""),
                "duration_seconds": raw.get("duration_seconds", 0),
                "workflow": raw.get("workflow", ""),
            },
        )
