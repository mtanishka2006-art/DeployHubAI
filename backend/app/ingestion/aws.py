"""AWS connector — CloudWatch metrics/alarms and CloudTrail audit events."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent


class AWSConnector(BaseConnector):
    """Ingests both CloudWatch (metrics) and CloudTrail (audit) records.

    The raw record's ``stream`` field selects the path; production would use
    boto3 ``cloudwatch.get_metric_data`` and ``cloudtrail.lookup_events`` with
    an assumed IAM role from ``self.config``.
    """

    source = "aws"

    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        return self.config.get("sample", [])

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        stream = raw.get("stream", "cloudwatch")
        if stream == "cloudtrail":
            return UnifiedEvent(
                source="aws_cloudtrail",
                event_type=EventType.AUDIT.value,
                timestamp=raw.get("timestamp") or datetime.now(timezone.utc),
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
            timestamp=raw.get("timestamp") or datetime.now(timezone.utc),
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
