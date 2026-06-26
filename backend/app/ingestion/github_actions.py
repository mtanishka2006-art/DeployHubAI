"""GitHub Actions connector — ingests workflow run results.

Live mode (when owner/repo/token are supplied) calls the GitHub REST API; with
no credentials it falls back to ``config['sample']`` so seeding/tests still work.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

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
                follow_redirects=True,
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
            r = httpx.get(url, headers=_headers(token), timeout=15,
                          follow_redirects=True)
            r.raise_for_status()
            runs = r.json().get("workflow_runs", [])
        except Exception as exc:  # noqa: BLE001
            self.log.warning("GitHub fetch failed: %s", exc)
            return []

        records: List[Dict[str, Any]] = []
        latest_by_wf: Dict[str, Dict[str, Any]] = {}
        for run in runs:  # the API returns newest first
            rec = {
                "repository": repo,
                "workflow": run.get("name"),
                "conclusion": run.get("conclusion") or "in_progress",
                "actor": (run.get("actor") or {}).get("login", ""),
                "head_sha": run.get("head_sha", ""),
                "run_number": str(run.get("run_number", "")),
                "created_at": run.get("run_started_at") or run.get("created_at"),
                "environment": "prod",
                "kind": "deployment",
            }
            records.append(rec)
            latest_by_wf.setdefault(rec["workflow"] or "workflow", rec)

        # The LATEST run per workflow decides incident state: a failing latest
        # run opens an incident; a passing one resolves the open incident.
        for rec in latest_by_wf.values():
            concl = (rec.get("conclusion") or "").lower()
            if concl == "failure":
                records.append({**rec, "kind": "incident"})
            elif concl == "success":
                records.append({**rec, "kind": "resolve"})
        return records

    def fetch_workflows(self) -> List[Dict[str, str]]:
        """List the repo's GitHub Actions workflow definitions (for Pipelines)."""
        if not self._has("owner", "repo"):
            return []
        owner, repo = self.config["owner"], self.config["repo"]
        token = self.config.get("token", "")
        try:
            r = httpx.get(
                f"{_API}/repos/{owner}/{repo}/actions/workflows",
                headers=_headers(token), timeout=15, follow_redirects=True,
            )
            r.raise_for_status()
            wfs = r.json().get("workflows", [])
        except Exception as exc:  # noqa: BLE001
            self.log.warning("GitHub workflows fetch failed: %s", exc)
            return []
        return [
            {"name": w.get("name") or w.get("path", "workflow"),
             "path": w.get("path", ""), "state": w.get("state", "active")}
            for w in wfs
        ]

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        kind = raw.get("kind", "deployment")
        ts = raw.get("created_at") or datetime.now(timezone.utc)
        repo = raw.get("repository", raw.get("workflow", "unknown"))
        wf = raw.get("workflow", "") or "workflow"
        sig = f"workflow '{wf}' failing"

        if kind == "incident":
            desc = (
                f"GitHub Actions workflow '{wf}' run #{raw.get('run_number', '?')} "
                f"FAILED on {repo} (commit {(raw.get('head_sha', '') or '')[:8]}, "
                f"by {raw.get('actor', '') or 'unknown'})."
            )
            return UnifiedEvent(
                source=self.source, event_type=EventType.LOG.value, timestamp=ts,
                severity="high", environment="prod", service=repo,
                metadata={"level": "error", "message": desc,
                          "error_signature": sig},
            )
        if kind == "resolve":
            return UnifiedEvent(
                source=self.source, event_type=EventType.LOG.value, timestamp=ts,
                severity="info", environment="prod", service=repo,
                metadata={"message": f"workflow '{wf}' recovered (latest run passed)",
                          "error_signature": sig, "resolve": True},
            )

        conclusion = (raw.get("conclusion") or "success").lower()
        status = {
            "success": "success",
            "failure": "failed",
            "cancelled": "rolled_back",
        }.get(conclusion, "in_progress")
        return UnifiedEvent(
            source=self.source,
            event_type=EventType.DEPLOYMENT.value,
            timestamp=ts,
            severity="high" if status == "failed" else "info",
            environment=raw.get("environment", "prod"),
            service=repo,
            metadata={
                "status": status,
                "actor": raw.get("actor", ""),
                "commit": (raw.get("head_sha", "") or "")[:12],
                "version": raw.get("run_number", ""),
                "duration_seconds": raw.get("duration_seconds", 0),
                "workflow": wf,
            },
        )
