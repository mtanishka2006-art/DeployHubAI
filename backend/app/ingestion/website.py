"""Website Monitor connector — synthetic uptime/performance checks for a live URL.

Unlike the git-import path (which infers telemetry from commit history), this is
genuinely live: the background poller re-probes the URL on a schedule and emits
real runtime telemetry — availability, response time, HTTP status, error rate —
plus an incident-grade log when the site is down, errors, or is slow. So Health,
Incidents, Metrics and Mission Control reflect the real running website.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import urlparse

import httpx

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent


def _service_name(url: str) -> str:
    host = urlparse(url).netloc or url
    return host[4:] if host.startswith("www.") else host or "website"


class WebsiteConnector(BaseConnector):
    source = "website"

    def _url(self) -> str:
        url = (self.config.get("url") or "").strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    def test_connection(self) -> Tuple[bool, str]:
        url = self._url()
        if not url:
            return False, "url is required"
        try:
            r = httpx.get(url, timeout=10, follow_redirects=True)
        except httpx.HTTPError as exc:
            return False, f"could not reach {url}: {exc}"
        return True, f"reachable — HTTP {r.status_code}"

    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        url = self._url()
        if not url:
            return []
        svc = _service_name(url)
        now = datetime.now(timezone.utc).isoformat()

        status_code = 0
        elapsed_ms = 0.0
        error = ""
        start = time.perf_counter()
        try:
            r = httpx.get(url, timeout=15, follow_redirects=True)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            status_code = r.status_code
        except httpx.HTTPError as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            error = str(exc)

        down = bool(error) or status_code >= 500 or status_code == 0
        client_err = 400 <= status_code < 500
        up = not down

        # error_rate feeds the monitoring agent's threshold (>=5 => anomaly), so
        # downtime/errors actually lower the health score.
        error_rate = 100.0 if down else (50.0 if client_err else 0.0)

        records: List[Dict[str, Any]] = [
            {"kind": "metric", "service": svc, "metric_name": "availability",
             "value": 100.0 if up else 0.0, "unit": "Percent", "ts": now},
            {"kind": "metric", "service": svc, "metric_name": "latency_p99",
             "value": round(elapsed_ms, 1), "unit": "Milliseconds", "ts": now},
            {"kind": "metric", "service": svc, "metric_name": "status_code",
             "value": float(status_code), "unit": "Count", "ts": now},
            {"kind": "metric", "service": svc, "metric_name": "error_rate",
             "value": error_rate, "unit": "Percent", "ts": now},
        ]

        # Incident-grade log when the site is unhealthy.
        if down:
            detail = error or f"HTTP {status_code}"
            records.append({
                "kind": "log", "service": svc, "severity": "critical",
                "message": f"{svc} is DOWN: {detail}", "ts": now,
            })
        elif client_err:
            records.append({
                "kind": "log", "service": svc, "severity": "high",
                "message": f"{svc} returned HTTP {status_code}", "ts": now,
            })
        elif elapsed_ms > 1500:
            records.append({
                "kind": "log", "service": svc, "severity": "high",
                "message": f"{svc} slow response: {elapsed_ms:.0f}ms", "ts": now,
            })
        return records

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        if raw.get("kind") == "log":
            msg = raw.get("message", "")
            return UnifiedEvent(
                source=self.source, event_type=EventType.LOG.value,
                timestamp=raw.get("ts"), severity=raw.get("severity", "high"),
                service=raw["service"], environment="prod",
                metadata={"message": msg, "error_signature": msg[:60]},
            )
        return UnifiedEvent(
            source=self.source, event_type=EventType.METRIC.value,
            timestamp=raw.get("ts"), severity="info",
            service=raw["service"], environment="prod",
            metadata={"metric_name": raw["metric_name"], "value": raw["value"],
                      "unit": raw.get("unit", "")},
        )
