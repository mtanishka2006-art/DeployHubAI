"""Datadog connector — ingests alerting monitors and host metrics.

Monitors in an Alert state become incidents; host metrics (CPU, memory, …)
become metric events so the host shows up as a service with live health.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

import httpx

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent

# Host metrics to pull as live telemetry (metric query -> unit shown in DeployHub).
_METRICS = [
    ("avg:system.cpu.user{*}by{host}", "system.cpu.user", "Percent"),
    ("avg:system.mem.used{*}by{host}", "system.mem.used", "Bytes"),
    ("avg:system.load.1{*}by{host}", "system.load.1", "Count"),
]


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
        # Fetch ALL monitors: alerting/warn ones -> incidents; monitors back in
        # OK state -> a resolve marker so a previously-opened incident closes.
        try:
            r = httpx.get(
                f"{self._base()}/api/v1/monitor",
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            for m in r.json():
                state = (m.get("overall_state") or "").lower()
                svc = (m.get("tags") or ["datadog"])[0] if m.get("tags") else "datadog"
                name = m.get("name", "Datadog monitor")
                if state in ("alert", "warn"):
                    records.append({
                        "kind": "monitor", "name": name, "state": state,
                        "service": svc, "message": m.get("message", ""),
                    })
                elif state == "ok":
                    records.append({
                        "kind": "monitor_resolve", "name": name, "service": svc,
                    })
        except Exception as exc:  # noqa: BLE001
            self.log.warning("Datadog monitor fetch failed: %s", exc)

        # Host metrics -> metric events (so the host appears as a service).
        records.extend(self._fetch_metrics())
        return records

    def _fetch_metrics(self) -> List[Dict[str, Any]]:
        """Pull the latest value per host for a few key system metrics via the
        Datadog timeseries query API."""
        out: List[Dict[str, Any]] = []
        now = int(time.time())
        frm = now - 600  # last 10 minutes
        for query, metric_name, unit in _METRICS:
            try:
                r = httpx.get(
                    f"{self._base()}/api/v1/query",
                    params={"from": frm, "to": now, "query": query},
                    headers=self._headers(),
                    timeout=15,
                )
                r.raise_for_status()
                series = r.json().get("series", []) or []
            except Exception as exc:  # noqa: BLE001
                self.log.warning("Datadog metric '%s' fetch failed: %s", metric_name, exc)
                continue
            for s in series:
                points = [p for p in (s.get("pointlist") or []) if p and p[1] is not None]
                if not points:
                    continue
                host = self._host_from_scope(s.get("scope", ""))
                out.append({
                    "stream": "metric",
                    "service": host,
                    "metric_name": metric_name,
                    "value": float(points[-1][1]),  # most recent point
                    "unit": unit,
                })
        return out

    @staticmethod
    def _host_from_scope(scope: str) -> str:
        """Datadog series scope looks like 'host:LAPTOP-XYZ' — extract the host."""
        for part in (scope or "").split(","):
            part = part.strip()
            if part.startswith("host:"):
                return part[len("host:"):] or "datadog-host"
        return scope or "datadog-host"

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        if raw.get("kind") in ("monitor", "monitor_resolve"):
            is_resolve = raw.get("kind") == "monitor_resolve"
            severity = (
                "info" if is_resolve
                else ("critical" if raw.get("state") == "alert" else "high")
            )
            meta = {
                "level": "info" if is_resolve else "error",
                "message": raw.get("name", "Datadog monitor"),
                "error_signature": str(raw.get("name", ""))[:60],
            }
            if is_resolve:
                meta["resolve"] = True  # closes the matching open incident
            return UnifiedEvent(
                source=self.source,
                event_type=EventType.LOG.value,
                timestamp=datetime.now(timezone.utc),
                severity=severity,
                environment="prod",
                service=str(raw.get("service", "datadog")).replace("service:", ""),
                metadata=meta,
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
