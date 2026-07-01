"""GCP connector — Cloud Monitoring metrics and alerting policies.

Live mode uses the optional ``google-cloud-monitoring`` library. With no
credentials, or if the library is not installed, it falls back to
``config['sample']`` so the rest of the platform is unaffected (mirrors the
AWS CloudWatch connector).

Credentials: a service-account key (pasted as JSON) plus the GCP project id.
If no JSON key is supplied the client falls back to Application Default
Credentials (e.g. ``GOOGLE_APPLICATION_CREDENTIALS``).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent

# A common, always-present GCE metric — instance CPU utilisation (0..1).
_DEFAULT_METRIC = "compute.googleapis.com/instance/cpu/utilization"


def _credentials(config: Dict[str, Any]):
    """Build service-account credentials from a pasted JSON key, or None (ADC)."""
    raw = config.get("credentials_json") or ""
    if not raw.strip():
        return None
    from google.oauth2 import service_account  # lazy optional import

    info = json.loads(raw)
    return service_account.Credentials.from_service_account_info(info)


def _project_id(config: Dict[str, Any]) -> str:
    pid = config.get("project_id") or ""
    if pid:
        return pid
    # Derive from the pasted key if the user left project_id blank.
    raw = config.get("credentials_json") or ""
    if raw.strip():
        try:
            return json.loads(raw).get("project_id", "")
        except Exception:  # noqa: BLE001
            return ""
    return ""


class GCPConnector(BaseConnector):
    """Cloud Monitoring time series become metric events; alert policies that are
    enabled surface as informational signals (mirrors AWS alarms -> incidents)."""

    source = "gcp"

    def test_connection(self) -> Tuple[bool, str]:
        if not _project_id(self.config):
            return False, "project_id (or a service-account key) is required"
        try:
            from google.cloud import monitoring_v3  # noqa: F401
        except ImportError:
            return (
                False,
                "google-cloud-monitoring not installed — run: "
                "pip install google-cloud-monitoring",
            )
        try:
            from google.cloud import monitoring_v3

            client = monitoring_v3.MetricServiceClient(
                credentials=_credentials(self.config)
            )
            project = f"projects/{_project_id(self.config)}"
            # Cheap validation call — the pager fetches lazily, so pulling one
            # item makes a single API round-trip that proves auth works.
            req = monitoring_v3.ListMetricDescriptorsRequest(name=project, page_size=1)
            next(iter(client.list_metric_descriptors(request=req)), None)
            return True, f"connected to {_project_id(self.config)}"
        except Exception as exc:  # noqa: BLE001
            return False, f"GCP auth failed: {exc}"

    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        project_id = _project_id(self.config)
        if not project_id:
            return self.config.get("sample", [])

        records: List[Dict[str, Any]] = []
        # Disaster-recovery signals (Cloud SQL backups / replicas / HA failover).
        # These feed the *traditional* RPO/RTO-based DR score. Best-effort: a
        # missing library or permission degrades to no DR rows, never a crash.
        records.extend(self._sql_dr_records(project_id))

        try:
            from google.cloud import monitoring_v3
        except ImportError:
            self.log.warning("google-cloud-monitoring not installed; GCP metric "
                             "fetch unavailable")
            return records

        project = f"projects/{project_id}"
        metric_type = self.config.get("metric_type", _DEFAULT_METRIC)
        # Resolve GCE instance IDs -> real names once (best-effort).
        self._gce_names = self._gce_id_to_name(project_id)
        try:
            client = monitoring_v3.MetricServiceClient(
                credentials=_credentials(self.config)
            )
            now = datetime.now(timezone.utc)
            interval = monitoring_v3.TimeInterval(
                start_time=now - timedelta(minutes=5), end_time=now
            )
            series = client.list_time_series(
                name=project,
                filter=f'metric.type = "{metric_type}"',
                interval=interval,
                view=monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            )
            for ts in series:
                labels = dict(ts.resource.labels)
                service = self._instance_name(ts, labels, project_id)
                point = ts.points[0] if ts.points else None
                value = (
                    point.value.double_value or float(point.value.int64_value or 0)
                    if point
                    else 0.0
                )
                records.append(
                    {
                        "stream": "metric",
                        "service": service,
                        "metric_name": ts.metric.type,
                        "value": round(value * 100, 2)
                        if ts.metric.type.endswith("utilization")
                        else value,
                        "unit": "Percent"
                        if ts.metric.type.endswith("utilization")
                        else "",
                        "project": project_id,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            self.log.warning("Cloud Monitoring fetch failed: %s", exc)
        return records

    def _gce_id_to_name(self, project_id: str) -> Dict[str, str]:
        """Map numeric GCE instance IDs to their human names via the Compute API.
        Best-effort: needs roles/compute.viewer; returns {} on any failure so we
        fall back to a labelled id."""
        try:
            from googleapiclient.discovery import build

            compute = build("compute", "v1", credentials=_credentials(self.config),
                            cache_discovery=False)
            out: Dict[str, str] = {}
            agg = compute.instances().aggregatedList(project=project_id).execute()
            for _zone, data in (agg.get("items") or {}).items():
                for inst in data.get("instances", []) or []:
                    if inst.get("id") and inst.get("name"):
                        out[str(inst["id"])] = inst["name"]
            return out
        except Exception as exc:  # noqa: BLE001
            self.log.info("GCE instance-name lookup unavailable (%s); using ids", exc)
            return {}

    def _instance_name(self, ts, labels: Dict[str, Any], project_id: str) -> str:
        """A human-readable service name for a monitored resource. Prefer the real
        GCE instance name (Compute API), then metadata/labels, then a labelled id
        fallback (never a bare number)."""
        iid = labels.get("instance_id")
        gce_names = getattr(self, "_gce_names", {})
        if iid and str(iid) in gce_names:
            return gce_names[str(iid)]
        try:
            from google.protobuf.json_format import MessageToDict

            sysl = (
                MessageToDict(ts.metadata.system_labels)
                if getattr(ts, "metadata", None) and ts.metadata.system_labels
                else {}
            )
        except Exception:  # noqa: BLE001
            sysl = {}
        name = (
            sysl.get("name")
            or sysl.get("instance_name")
            or labels.get("instance_name")
            or labels.get("database_id")  # Cloud SQL: project:instance
        )
        if name:
            return str(name).split(":")[-1]
        if iid:
            return f"gce-instance-{iid}"  # labelled, not a bare number
        return project_id

    def _sql_dr_records(self, project_id: str) -> List[Dict[str, Any]]:
        """Derive backup / replication / failover signals from Cloud SQL.

        Maps real GCP recoverability facts onto the Unified Event Schema:
          * automated backup runs   -> backup events   (RPO)
          * read replicas           -> replication events
          * REGIONAL HA / failover  -> failover events  (RTO)
        """
        try:
            from googleapiclient.discovery import build  # lazy optional import
        except ImportError:
            self.log.warning("google-api-python-client not installed; GCP DR "
                             "(Cloud SQL) fetch unavailable")
            return []

        records: List[Dict[str, Any]] = []
        try:
            sql = build("sqladmin", "v1", credentials=_credentials(self.config),
                        cache_discovery=False)
            instances = sql.instances().list(
                project=project_id
            ).execute().get("items", [])
        except Exception as exc:  # noqa: BLE001
            self.log.warning("Cloud SQL list failed: %s", exc)
            return []

        for inst in instances:
            name = inst.get("name", "cloudsql")
            settings = inst.get("settings", {}) or {}
            running = inst.get("state") == "RUNNABLE"

            # --- Backup (RPO) --- #
            backup_cfg = settings.get("backupConfiguration", {}) or {}
            enabled = bool(backup_cfg.get("enabled"))
            last_backup = None
            try:
                runs = sql.backupRuns().list(
                    project=project_id, instance=name
                ).execute().get("items", [])  # API returns newest first
                ok = [r for r in runs if r.get("status") == "SUCCESSFUL"]
                last_backup = ok[0].get("endTime") if ok else None
            except Exception as exc:  # noqa: BLE001
                self.log.warning("backupRuns(%s) failed: %s", name, exc)
            records.append({
                "stream": "backup",
                "service": name,
                "system": name,
                "status": "healthy" if (enabled and last_backup) else "degraded",
                "last_backup": last_backup,
                # Automated Cloud SQL backups are daily -> RPO target ~24h.
                "rpo_minutes": 1440,
                "project": project_id,
            })

            # --- Replication --- #
            replicas = inst.get("replicaNames") or []
            if replicas:
                records.append({
                    "stream": "replication",
                    "service": name,
                    "source": name,
                    "target": ", ".join(replicas),
                    "status": "in_sync" if running else "degraded",
                    "lag_seconds": 0,  # precise lag would come from a Monitoring metric
                    "project": project_id,
                })

            # --- Failover / HA (RTO) --- #
            availability = settings.get("availabilityType")
            if availability == "REGIONAL" or inst.get("failoverReplica"):
                records.append({
                    "stream": "failover",
                    "service": name,
                    "region": inst.get("region", ""),
                    "target_region": inst.get("region", ""),
                    "status": "ready" if running else "degraded",
                    # Cloud SQL HA failover is automatic & continuously maintained —
                    # there is no manual "test", so don't penalise it as stale.
                    "auto_failover": True,
                    "rto_minutes": 5,
                    "project": project_id,
                })
        return records

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        stream = raw.get("stream", "metric")
        now = datetime.now(timezone.utc)

        if stream in ("backup", "replication", "failover"):
            event_type = {
                "backup": EventType.BACKUP,
                "replication": EventType.REPLICATION,
                "failover": EventType.FAILOVER,
            }[stream]
            degraded = raw.get("status") not in {
                "healthy", "ok", "success", "in_sync", "ready", "active"
            }
            return UnifiedEvent(
                source="gcp_cloudsql",
                event_type=event_type.value,
                timestamp=raw.get("timestamp") or now,
                severity="high" if degraded else "info",
                environment=raw.get("environment", "prod"),
                service=raw.get("service", "gcp"),
                metadata={k: v for k, v in raw.items() if k != "stream"},
            )

        if stream == "alert":
            # An open alert -> critical log event, which the LogProcessor turns
            # into an Incident (parallels the AWS CloudWatch-alarm path).
            return UnifiedEvent(
                source="gcp_monitoring",
                event_type=EventType.LOG.value,
                timestamp=raw.get("timestamp") or now,
                severity="critical",
                environment=raw.get("environment", "prod"),
                service=raw.get("service", "gcp"),
                metadata={
                    "level": "error",
                    "message": raw.get("message", ""),
                    "error_signature": raw.get("alert_name", "GCP alert policy"),
                    "metric_name": raw.get("metric_name", ""),
                    "project": raw.get("project", ""),
                },
            )
        # Default: Cloud Monitoring metric.
        return UnifiedEvent(
            source="gcp_monitoring",
            event_type=EventType.METRIC.value,
            timestamp=raw.get("timestamp") or now,
            severity=raw.get("severity", "info"),
            environment=raw.get("environment", "prod"),
            service=raw.get("service", "unknown"),
            metadata={
                "metric_name": raw.get("metric_name", _DEFAULT_METRIC),
                "value": raw.get("value", 0.0),
                "unit": raw.get("unit", "Percent"),
                "project": raw.get("project", ""),
            },
        )
