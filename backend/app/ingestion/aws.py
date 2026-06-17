"""AWS connector — CloudWatch alarms (-> incidents) and metrics.

Live mode uses boto3 (optional dependency). With no credentials, or if boto3 is
not installed, it falls back to ``config['sample']`` so the rest of the platform
is unaffected.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent


def _session(config: Dict[str, Any]):
    import boto3  # imported lazily; optional dependency

    return boto3.Session(
        aws_access_key_id=config.get("access_key_id"),
        aws_secret_access_key=config.get("secret_access_key"),
        region_name=config.get("region", "us-east-1"),
    )


class AWSConnector(BaseConnector):
    """CloudWatch alarms become incidents; alarm metrics become metric events."""

    source = "aws"

    def test_connection(self) -> Tuple[bool, str]:
        if not self._has("access_key_id", "secret_access_key"):
            return False, "access_key_id and secret_access_key are required"
        try:
            import boto3  # noqa: F401
        except ImportError:
            return False, "boto3 not installed — run: pip install boto3"
        try:
            ident = _session(self.config).client("sts").get_caller_identity()
            return True, f"connected as {ident.get('Arn', 'aws account')}"
        except Exception as exc:  # noqa: BLE001
            return False, f"AWS auth failed: {exc}"

    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        if not self._has("access_key_id", "secret_access_key"):
            return self.config.get("sample", [])
        try:
            import boto3  # noqa: F401
        except ImportError:
            self.log.warning("boto3 not installed; AWS live fetch unavailable")
            return []

        region = self.config.get("region", "us-east-1")
        records: List[Dict[str, Any]] = []
        try:
            cw = _session(self.config).client("cloudwatch")
            alarms = cw.describe_alarms(
                StateValue="ALARM", MaxRecords=50
            ).get("MetricAlarms", [])
            for a in alarms:
                records.append(
                    {
                        "stream": "cloudwatch_alarm",
                        "alarm_name": a.get("AlarmName", "CloudWatch alarm"),
                        "service": a.get("Namespace", "aws"),
                        "metric_name": a.get("MetricName", ""),
                        "message": a.get("StateReason", a.get("AlarmDescription", "")),
                        "region": region,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            self.log.warning("CloudWatch fetch failed: %s", exc)
        return records

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        stream = raw.get("stream", "cloudwatch")
        now = datetime.now(timezone.utc)

        if stream == "cloudwatch_alarm":
            # An active alarm -> a critical log event, which the LogProcessor
            # turns into an Incident.
            return UnifiedEvent(
                source="aws_cloudwatch",
                event_type=EventType.LOG.value,
                timestamp=raw.get("timestamp") or now,
                severity="critical",
                environment=raw.get("environment", "prod"),
                service=raw.get("service", "aws"),
                metadata={
                    "level": "error",
                    "message": raw.get("message", ""),
                    "error_signature": raw.get("alarm_name", "CloudWatch alarm"),
                    "metric_name": raw.get("metric_name", ""),
                    "region": raw.get("region", "us-east-1"),
                },
            )
        if stream == "cloudtrail":
            return UnifiedEvent(
                source="aws_cloudtrail",
                event_type=EventType.AUDIT.value,
                timestamp=raw.get("timestamp") or now,
                severity=raw.get("severity", "info"),
                environment=raw.get("environment", "prod"),
                service=raw.get("event_source", "aws"),
                metadata={
                    "event_name": raw.get("event_name"),
                    "user_identity": raw.get("user_identity"),
                    "region": raw.get("region", "us-east-1"),
                    "source_ip": raw.get("source_ip"),
                },
            )
        # Default: CloudWatch metric.
        return UnifiedEvent(
            source="aws_cloudwatch",
            event_type=EventType.METRIC.value,
            timestamp=raw.get("timestamp") or now,
            severity=raw.get("severity", "info"),
            environment=raw.get("environment", "prod"),
            service=raw.get("service", "unknown"),
            metadata={
                "metric_name": raw.get("metric_name", "CPUUtilization"),
                "value": raw.get("value", 0.0),
                "unit": raw.get("unit", "Percent"),
                "region": raw.get("region", "us-east-1"),
            },
        )
