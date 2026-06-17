"""Rich, realistic sample-data ingestion + self-test.

Pushes a coherent batch of records across all 7 connectors through the real
pipeline (normalize -> processor -> DB), then runs Mission Control and a memory
search to prove the ingested data flows all the way through the agents.

    python -m scripts.ingest_sample
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.ingestion.registry import get_connector
from app.processing.deployment_processor import DeploymentProcessor
from app.processing.dr_processor import DisasterRecoveryProcessor
from app.processing.log_processor import LogProcessor
from app.processing.metric_processor import MetricProcessor
from app.schemas.events import EventType

NOW = datetime.now(timezone.utc)


def _ago(minutes: int) -> datetime:
    return NOW - timedelta(minutes=minutes)


# --------------------------------------------------------------------------- #
# Sample records per source — a coherent "bad afternoon for order-service".
# --------------------------------------------------------------------------- #
SAMPLES = {
    "github_actions": [
        {
            "repository": "order-service",
            "conclusion": "failure",
            "actor": "dev-jane",
            "head_sha": "a1b2c3d4e5f6",
            "run_number": "3.2.0",
            "duration_seconds": 310,
            "environment": "prod",
            "created_at": _ago(35),
        },
        {
            "repository": "search-service",
            "conclusion": "success",
            "actor": "dev-omar",
            "head_sha": "ff00aa11bb22",
            "run_number": "0.8.6",
            "duration_seconds": 142,
            "environment": "prod",
            "created_at": _ago(180),
        },
    ],
    "jenkins": [
        {
            "job_name": "analytics-service",
            "number": 88,
            "result": "ABORTED",
            "duration": 95000,
            "actor": "ci-bot",
            "version": "2.0.1",
            "commit": "7c1d9e0",
            "environment": "staging",
            "timestamp": _ago(220),
        }
    ],
    "aws": [
        {
            "stream": "cloudwatch",
            "service": "order-service",
            "metric_name": "CPUUtilization",
            "value": 94.7,
            "unit": "Percent",
            "region": "us-east-1",
            "environment": "prod",
            "timestamp": _ago(30),
        },
        {
            "stream": "cloudwatch",
            "service": "order-service",
            "metric_name": "error_rate",
            "value": 11.2,
            "unit": "Percent",
            "region": "us-east-1",
            "environment": "prod",
            "timestamp": _ago(28),
        },
        {
            "stream": "cloudtrail",
            "event_name": "StopInstances",
            "user_identity": "ops-admin",
            "region": "us-east-1",
            "source_ip": "10.2.4.9",
            "environment": "prod",
            "severity": "medium",
            "timestamp": _ago(50),
        },
    ],
    "azure": [
        {
            "stream": "monitor",
            "service": "notification-service",
            "metric_name": "Percentage CPU",
            "value": 41.0,
            "unit": "Percent",
            "region": "eastus",
            "environment": "prod",
            "timestamp": _ago(20),
        }
    ],
    "kubernetes": [
        {
            "kind": "event",
            "workload": "order-service",
            "reason": "CrashLoopBackOff",
            "message": "Back-off restarting failed container order after NullPointerException",
            "namespace": "prod",
            "pod": "order-5f7c-x9a2",
            "environment": "prod",
            "timestamp": _ago(32),
        },
        {
            "kind": "metric",
            "service": "order-service",
            "metric_name": "pod_memory",
            "value": 1.85,
            "unit": "GiB",
            "namespace": "prod",
            "environment": "prod",
            "timestamp": _ago(25),
        },
    ],
    "logs": [
        {
            "level": "ERROR",
            "service": "search-service",
            "message": "ElasticTimeoutException: query timed out after 30s",
            "host": "search-node-3",
            "environment": "prod",
            "timestamp": _ago(15),
        },
        {
            "level": "INFO",
            "service": "user-service",
            "message": "health check ok",
            "host": "user-node-1",
            "environment": "prod",
            "timestamp": _ago(10),
        },
    ],
    "disaster_recovery": [
        {
            "dr_type": "backup",
            "system": "analytics-warehouse-backup",
            "service": "analytics-service",
            "status": "stale",
            "rpo_minutes": 1440,
            "size_gb": 980.0,
            "last_backup": _ago(60 * 40),
            "environment": "prod",
            "timestamp": _ago(60),
        },
        {
            "dr_type": "replication",
            "source": "postgres-primary",
            "target": "postgres-replica",
            "status": "lagging",
            "lag_seconds": 540,
            "environment": "prod",
            "timestamp": _ago(12),
        },
        {
            "dr_type": "failover",
            "service": "order-service",
            "region": "us-east-1",
            "target_region": "us-west-2",
            "status": "ready",
            "rto_minutes": 20,
            "last_tested": _ago(60 * 24 * 30),
            "environment": "prod",
            "timestamp": _ago(60),
        },
        {
            "dr_type": "dr_event",
            "event_type": "replication_warning",
            "service": "postgres-primary",
            "region": "us-east-1",
            "status": "degraded",
            "detail": "Replication lag exceeded 5 minutes during bulk import",
            "environment": "prod",
            "timestamp": _ago(11),
        },
    ],
}


def processor_for(event_type: str, db):
    if event_type == EventType.METRIC.value:
        return MetricProcessor(db)
    if event_type == EventType.LOG.value:
        return LogProcessor(db)
    if event_type == EventType.DEPLOYMENT.value:
        return DeploymentProcessor(db)
    if event_type == EventType.AUDIT.value:
        return MetricProcessor(db)  # audit events tracked as metric/log signal
    return DisasterRecoveryProcessor(db)


def ingest(db) -> int:
    total = 0
    for source, records in SAMPLES.items():
        connector = get_connector(source, {"sample": records})
        for event in connector.collect():
            proc = processor_for(event.event_type, db)
            try:
                obj = proc.process(event)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {source}/{event.event_type} skipped: {exc}")
                continue
            total += 1
            print(
                f"[{source:17}] {event.event_type:11} {event.service:20} "
                f"sev={event.severity:8} -> {type(obj).__name__}#{getattr(obj, 'id', '?')}"
            )
    db.commit()
    return total


def selftest(db) -> None:
    from app.db.models import (
        Backup,
        Deployment,
        DisasterRecoveryEvent,
        FailoverEvent,
        Incident,
        InfrastructureMetric,
        ReplicationStatus,
    )
    from app.mission_control.orchestrator import MissionControl
    from app.memory.infrastructure_memory import get_memory

    print("\n=== DB row counts ===")
    for model in (
        InfrastructureMetric, Incident, Deployment, Backup,
        FailoverEvent, ReplicationStatus, DisasterRecoveryEvent,
    ):
        print(f"  {model.__name__:24} {db.query(model).count()}")

    print("\n=== Mission Control on order-service ===")
    mc = MissionControl(db)
    report = mc.run(
        {
            "service": "order-service",
            "description": "order-service CrashLoopBackOff + 5xx after v3.2.0",
            "severity": "critical",
        }
    )
    print("  system_health :", report["system_health"])
    print("  root_cause    :", report["root_cause"])
    print("  dr_readiness  :", report["dr_readiness"])
    print("  #actions      :", len(report["recommended_actions"]))
    if report["recommended_actions"]:
        print("  top action    :", report["recommended_actions"][0]["action"])

    print("\n=== Memory search: 'crashloop order-service after deploy' ===")
    for hit in get_memory().search_similar_incidents(
        "crashloop order-service after deploy", k=3
    ):
        print(f"  [{hit['score']:.2f}] {hit['title']}")


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        print("--- Ingesting sample data through the connector pipeline ---")
        n = ingest(db)
        print(f"\nIngested {n} events.")
        selftest(db)
        print("\nDONE — refresh the dashboard.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
