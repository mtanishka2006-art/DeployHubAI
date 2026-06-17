"""End-to-end ingestion demo.

Pushes raw records from several sources through the REAL pipeline:

    raw record -> Connector.collect() (normalize) -> Processor.process() -> DB

Run it (with the venv active) from the backend/ directory:

    python -m scripts.ingest_demo

Then refresh the dashboard — the new deployment, metric spike, K8s incident and
DR event will appear. This is the same code path a production poller/webhook
would use; only `fetch_raw()` differs (live API call vs. these sample records).

To insert YOUR OWN data, edit the `RAW_*` lists below: each dict is one raw
record in the upstream system's native shape, exactly as that system emits it.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.ingestion.registry import get_connector
from app.processing.deployment_processor import DeploymentProcessor
from app.processing.dr_processor import DisasterRecoveryProcessor
from app.processing.log_processor import LogProcessor
from app.processing.metric_processor import MetricProcessor
from app.schemas.events import EventType

# --------------------------------------------------------------------------- #
# 1. RAW records — the native shape each source emits. EDIT THESE.
# --------------------------------------------------------------------------- #
NOW = datetime.now(timezone.utc)

RAW_JENKINS = [
    {
        "job_name": "payments-service",
        "number": 412,
        "result": "FAILURE",           # -> normalized to status "failed"
        "duration": 240000,            # ms
        "actor": "ci-bot",
        "commit": "9f3ab21",
        "version": "1.9.4",
        "environment": "prod",
        "timestamp": NOW,
    },
     {
        "job_name": "transport-service",
        "number": 407,
        "result": "FAILURE",           # -> normalized to status "failed"
        "duration": 240000,            # ms
        "actor": "ci-bot",
        "commit": "9f3ab21",
        "version": "1.9.4",
        "environment": "prod",
        "timestamp": NOW,
    }

]

RAW_CLOUDWATCH = [
    {
        "stream": "cloudwatch",
        "service": "payments-service",
        "metric_name": "CPUUtilization",
        "value": 96.4,                 # a spike the Monitoring agent will flag
        "unit": "Percent",
        "region": "us-east-1",
        "environment": "prod",
        "timestamp": NOW,
    }
]

RAW_K8S = [
    {
        "kind": "event",
        "workload": "payments-service",
        "reason": "OOMKilled",         # a "bad reason" -> severity critical
        "message": "Container payments exceeded memory limit and was killed",
        "namespace": "prod",
        "pod": "payments-7d9c-abcde",
        "environment": "prod",
        "timestamp": NOW,
    }
]

RAW_DR = [
    {
        "dr_type": "backup",
        "system": "rds-snapshot",
        "service": "postgres-primary",
        "status": "healthy",
        "rpo_minutes": 60,
        "size_gb": 425.0,
        "last_backup": NOW,
        "environment": "prod",
        "timestamp": NOW,
    }
]

# --------------------------------------------------------------------------- #
# 2. Route each normalized event to the right processor.
# --------------------------------------------------------------------------- #
def processor_for(event_type: str, db):
    if event_type == EventType.METRIC.value:
        return MetricProcessor(db)
    if event_type == EventType.LOG.value:
        return LogProcessor(db)
    if event_type == EventType.DEPLOYMENT.value:
        return DeploymentProcessor(db)
    # backup / failover / replication / dr_event
    return DisasterRecoveryProcessor(db)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    total = 0
    try:
        batches = [
            ("jenkins", RAW_JENKINS),
            ("aws", RAW_CLOUDWATCH),
            ("kubernetes", RAW_K8S),
            ("disaster_recovery", RAW_DR),
        ]
        for source, raw_records in batches:
            # fetch_raw() reads config["sample"], so we inject our raw records there.
            connector = get_connector(source, {"sample": raw_records})
            events = connector.collect()      # fetch + normalize + retry
            for event in events:
                proc = processor_for(event.event_type, db)
                obj = proc.process(event)      # clean -> enrich -> persist -> embed
                total += 1
                print(
                    f"[{source}] {event.event_type:11} {event.service:18} "
                    f"sev={event.severity:8} -> {type(obj).__name__}#{getattr(obj, 'id', '?')}"
                )
        db.commit()
        print(f"\nIngested {total} events. Refresh the dashboard to see them.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
