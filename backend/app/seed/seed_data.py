"""Realistic seed data so the dashboard is populated immediately after setup.

Generates: users (one per role), 24h of metrics across services, deployments
(incl. a failure), error logs that become incidents, backups, replication
status, failover config, and a corpus of resolved HistoricalIncidents that are
embedded into the vector memory for RAG.

Idempotent: running twice will not duplicate users; data tables are only seeded
when empty.
"""
from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.core.security import Role, hash_password
from app.db.base import utcnow
from app.db.models import (
    AgentOutput,
    Backup,
    ConnectedApp,
    ConnectorEvent,
    Deployment,
    DeploymentStatus,
    DisasterRecoveryEvent,
    FailoverEvent,
    HistoricalIncident,
    Incident,
    InfrastructureMetric,
    MissionControlReport,
    Pipeline,
    RecoveryAction,
    ReplicationStatus,
    Severity,
    SimulationReport,
    User,
)
from app.memory.infrastructure_memory import get_memory

logger = get_logger("seed")

_RNG = random.Random(42)  # deterministic seed data

SERVICES = [
    "api-gateway",
    "checkout-service",
    "payments-service",
    "order-service",
    "inventory-service",
    "user-service",
    "notification-service",
    "search-service",
]
METRICS = [
    ("CPUUtilization", "Percent", 20, 70),
    ("MemoryUtilization", "Percent", 30, 75),
    ("latency_p99", "ms", 80, 400),
    ("error_rate", "Percent", 0, 2),
]


def seed_users(db: Session) -> None:
    accounts = [
        (settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD, Role.ADMIN),
        ("sre", "sre", Role.SRE),
        ("devops", "devops", Role.DEVOPS),
        ("viewer", "viewer", Role.VIEWER),
    ]
    for username, password, role in accounts:
        if not db.query(User).filter(User.username == username).first():
            db.add(
                User(
                    username=username,
                    hashed_password=hash_password(password),
                    role=role.value,
                )
            )
    db.commit()
    logger.info("seeded users (admin/sre/devops/viewer)")


def seed_operational_data(db: Session) -> None:
    if db.scalar(select(func.count(InfrastructureMetric.id))):
        logger.info("operational data already present; skipping")
        return

    now = utcnow()

    # ---- Metrics: 24 hourly points per (service, metric) ----
    for svc in SERVICES:
        # Inject a degradation into checkout-service to make the demo lively.
        degraded = svc == "checkout-service"
        for name, unit, lo, hi in METRICS:
            for h in range(24, 0, -1):
                ts = now - timedelta(hours=h)
                base = _RNG.uniform(lo, hi)
                if degraded and h <= 3 and name in {"CPUUtilization", "error_rate"}:
                    base = hi + _RNG.uniform(15, 30)  # spike
                db.add(
                    InfrastructureMetric(
                        source="aws_cloudwatch",
                        service=svc,
                        environment="prod",
                        metric_name=name,
                        value=round(base, 2),
                        unit=unit,
                        timestamp=ts,
                    )
                )

    # ---- Deployments ----
    deploy_specs = [
        ("checkout-service", "2.4.1", "failed", "github_actions"),
        ("checkout-service", "2.4.0", "success", "github_actions"),
        ("payments-service", "1.9.3", "success", "jenkins"),
        ("order-service", "3.1.0", "success", "jenkins"),
        ("inventory-service", "1.2.7", "rolled_back", "github_actions"),
        ("user-service", "4.0.2", "success", "github_actions"),
        ("search-service", "0.8.5", "success", "jenkins"),
        ("api-gateway", "5.2.0", "success", "jenkins"),
    ]
    for i, (svc, ver, status, source) in enumerate(deploy_specs):
        db.add(
            Deployment(
                source=source,
                service=svc,
                environment="prod",
                version=ver,
                commit=f"{_RNG.randrange(16**7):07x}",
                actor=_RNG.choice(["alice", "bob", "carol", "ci-bot"]),
                status=status,
                duration_seconds=_RNG.randint(120, 900),
                timestamp=now - timedelta(hours=i * 2 + 1),
            )
        )

    # ---- Active incidents ----
    incidents = [
        Incident(
            title="checkout-service: HTTP 500 surge after v2.4.1",
            description="Error rate spiked to 30% and p99 latency exceeded 2s "
            "immediately after the v2.4.1 deployment.",
            severity=Severity.CRITICAL.value,
            status="investigating",
            service="checkout-service",
            environment="prod",
            source="github_actions",
            detected_at=now - timedelta(hours=2, minutes=40),
        ),
        Incident(
            title="inventory-service: elevated DB connection errors",
            description="Intermittent 'connection pool exhausted' errors against "
            "postgres-primary.",
            severity=Severity.HIGH.value,
            status="open",
            service="inventory-service",
            environment="prod",
            source="logs",
            detected_at=now - timedelta(hours=5),
        ),
    ]
    db.add_all(incidents)

    # ---- DR: backups / replication / failover ----
    db.add_all(
        [
            Backup(system="rds-snapshot", service="postgres-primary",
                   status="healthy", last_backup=now - timedelta(hours=1),
                   rpo_minutes=60, size_gb=420.0),
            Backup(system="s3-object-backup", service="assets",
                   status="healthy", last_backup=now - timedelta(hours=3),
                   rpo_minutes=240, size_gb=1200.0),
            Backup(system="velero-k8s", service="k8s:prod-east",
                   status="stale", last_backup=now - timedelta(hours=30),
                   rpo_minutes=120, size_gb=80.0),
        ]
    )
    db.add_all(
        [
            ReplicationStatus(source="postgres-primary", target="postgres-replica",
                              status="in_sync", lag_seconds=4,
                              timestamp=now - timedelta(minutes=2)),
            ReplicationStatus(source="aws:us-east-1", target="aws:us-west-2",
                              status="in_sync", lag_seconds=45,
                              timestamp=now - timedelta(minutes=2)),
        ]
    )
    db.add_all(
        [
            FailoverEvent(service="postgres-primary", region="us-east-1",
                          target_region="us-west-2", status="ready",
                          last_tested=now - timedelta(days=14), rto_minutes=15),
            FailoverEvent(service="k8s:prod-east", region="us-east-1",
                          target_region="us-west-2", status="ready",
                          last_tested=now - timedelta(days=120), rto_minutes=25),
            FailoverEvent(service="notification-service", region="eastus",
                          target_region="us-east-1", status="degraded",
                          last_tested=now - timedelta(days=200), rto_minutes=40),
        ]
    )
    db.add_all(
        [
            DisasterRecoveryEvent(event_type="backup_completed",
                                  service="postgres-primary", region="us-east-1",
                                  status="success", detail="Nightly RDS snapshot ok",
                                  timestamp=now - timedelta(hours=1)),
            DisasterRecoveryEvent(event_type="failover_test",
                                  service="postgres-primary", region="us-east-1",
                                  status="passed", detail="Quarterly DR drill passed",
                                  timestamp=now - timedelta(days=14)),
            DisasterRecoveryEvent(event_type="replication_warning",
                                  service="notification-service", region="eastus",
                                  status="degraded",
                                  detail="Cross-cloud replication lag rising",
                                  timestamp=now - timedelta(hours=6)),
        ]
    )
    db.commit()
    logger.info("seeded operational data (metrics, deployments, incidents, DR)")


def seed_historical_incidents(db: Session) -> None:
    if db.scalar(select(func.count(HistoricalIncident.id))):
        logger.info("historical incidents already present; skipping")
        return

    now = utcnow()
    corpus = [
        {
            "title": "Checkout 500s after bad deploy",
            "summary": "A checkout-service release introduced a null-pointer in "
            "the payment serializer causing 500s.",
            "root_cause": "Regression in deployment — unvalidated payment payload.",
            "recovery_actions": ["Rolled back to previous version",
                                 "Added contract test for payment payload"],
            "outcome": "Resolved in 18m by rollback; error rate returned to baseline.",
            "service": "checkout-service",
            "severity": "critical",
            "tags": ["deployment", "rollback", "checkout"],
        },
        {
            "title": "DB connection pool exhaustion",
            "summary": "inventory-service exhausted the Postgres connection pool "
            "under peak load.",
            "root_cause": "Connection leak + undersized pool after traffic growth.",
            "recovery_actions": ["Increased pool size", "Patched connection leak",
                                 "Added PgBouncer"],
            "outcome": "Resolved by config + patch; no recurrence.",
            "service": "inventory-service",
            "severity": "high",
            "tags": ["database", "connections", "saturation"],
        },
        {
            "title": "AWS us-east-1 partial outage",
            "summary": "An AZ disruption in us-east-1 degraded tier-0 services.",
            "root_cause": "Upstream cloud provider AZ failure.",
            "recovery_actions": ["Failed over to us-west-2", "Shifted DNS traffic",
                                 "Promoted DB replica"],
            "outcome": "Failover completed in 22m; minimal data loss within RPO.",
            "service": "platform",
            "severity": "critical",
            "tags": ["aws", "region", "failover", "dr"],
        },
        {
            "title": "Memory leak OOMKilled pods",
            "summary": "search-service pods were OOMKilled repeatedly.",
            "root_cause": "Unbounded in-memory cache growth.",
            "recovery_actions": ["Set memory limits + eviction", "Hotfixed cache"],
            "outcome": "Stabilized after hotfix and limits.",
            "service": "search-service",
            "severity": "high",
            "tags": ["kubernetes", "memory", "oom"],
        },
        {
            "title": "Replication lag spike",
            "summary": "Cross-region replication lag exceeded 10 minutes risking RPO.",
            "root_cause": "Network saturation during bulk import.",
            "recovery_actions": ["Throttled bulk import", "Scaled replica IO"],
            "outcome": "Lag recovered; RPO maintained.",
            "service": "postgres-primary",
            "severity": "medium",
            "tags": ["replication", "dr", "database"],
        },
    ]
    memory = get_memory()
    for i, c in enumerate(corpus):
        row = HistoricalIncident(
            title=c["title"],
            summary=c["summary"],
            root_cause=c["root_cause"],
            recovery_actions=c["recovery_actions"],
            outcome=c["outcome"],
            service=c["service"],
            severity=c["severity"],
            tags=c["tags"],
            occurred_at=now - timedelta(days=20 + i * 9),
            embedded=True,
        )
        db.add(row)
        db.flush()
        memory.store_incident(
            incident_id=f"hist-{row.id}",
            title=row.title,
            summary=row.summary,
            root_cause=row.root_cause,
            service=row.service,
            severity=row.severity,
            occurred_at=row.occurred_at.isoformat(),
            tags=row.tags,
        )
        memory.store_resolution(
            incident_id=f"hist-{row.id}",
            recovery_actions=row.recovery_actions,
            outcome=row.outcome,
            title=row.title,
            root_cause=row.root_cause,
            service=row.service,
        )
    db.commit()
    logger.info("seeded %d historical incidents into vector memory", len(corpus))


def sync_vector_memory(db: Session) -> None:
    """Re-embed incidents into the vector store when it is empty.

    The in-memory vector store (ChromaDB fallback) is volatile — it is lost on
    every process restart. The DB-backed rows survive, so on restart the seed's
    "table already populated" guard skips embedding and memory comes up empty.
    This repopulates memory from the durable tables so RAG search always works,
    regardless of how many times the server has restarted. Idempotent: it does
    nothing when the store already has vectors (first boot, or persistent Chroma).
    """
    memory = get_memory()
    if memory.stats().get("incident_memory", 0) > 0:
        return
    count = 0
    for row in db.query(HistoricalIncident).all():
        memory.store_incident(
            incident_id=f"hist-{row.id}",
            title=row.title,
            summary=row.summary,
            root_cause=row.root_cause,
            service=row.service,
            severity=row.severity,
            occurred_at=row.occurred_at.isoformat(),
            tags=row.tags,
        )
        memory.store_resolution(
            incident_id=f"hist-{row.id}",
            recovery_actions=row.recovery_actions,
            outcome=row.outcome,
            title=row.title,
            root_cause=row.root_cause,
            service=row.service,
        )
        count += 1
    # Also index live incidents so operators can find recently-ingested ones.
    for inc in db.query(Incident).all():
        memory.store_incident(
            incident_id=str(inc.id),
            title=inc.title,
            summary=inc.description or inc.title,
            root_cause=inc.root_cause or "",
            service=inc.service,
            severity=inc.severity,
            occurred_at=inc.detected_at.isoformat(),
        )
        count += 1
    # Deployment failures -> deployment_memory collection.
    for dep in (
        db.query(Deployment)
        .filter(Deployment.status.in_(["failed", "rolled_back"]))
        .all()
    ):
        memory.store_deployment_failure(
            deployment_id=str(dep.id),
            service=dep.service,
            summary=f"{dep.status} deployment v{dep.version}",
            root_cause="",
        )
        count += 1
    # Degraded/failed DR events -> dr_memory collection.
    for ev in (
        db.query(DisasterRecoveryEvent)
        .filter(DisasterRecoveryEvent.status.in_(["degraded", "failed"]))
        .all()
    ):
        memory.store_dr_incident(
            dr_id=str(ev.id),
            service=ev.service,
            summary=f"{ev.event_type} {ev.status}",
            outcome=ev.detail,
        )
        count += 1
    logger.info("synced %d records into vector memory", count)


def reset_platform_data(db: Session) -> None:
    """Wipe all operational data + connectors + vector memory (keeps users).

    Used when importing a project in 'replace' mode so the dashboards reflect
    ONLY the uploaded application. Deletes child rows before parents to stay
    safe regardless of FK cascade support (e.g. SQLite).
    """
    for model in (
        Pipeline,
        ConnectorEvent,
        ConnectedApp,
        RecoveryAction,
        AgentOutput,
        MissionControlReport,
        SimulationReport,
        Incident,
        Deployment,
        InfrastructureMetric,
        DisasterRecoveryEvent,
        Backup,
        FailoverEvent,
        ReplicationStatus,
        HistoricalIncident,
    ):
        db.query(model).delete(synchronize_session=False)
    db.commit()
    try:
        get_memory().reset()
    except Exception:  # noqa: BLE001
        logger.warning("vector memory reset skipped")
    logger.info("platform data reset (operational tables + memory cleared)")


def has_real_data(db: Session) -> bool:
    """True once the user has connected/imported a real source."""
    return db.query(ConnectedApp).count() > 0


def run_all(db: Session) -> None:
    seed_users(db)
    # Once the user has connected real apps, never re-add synthetic demo data.
    if has_real_data(db):
        sync_vector_memory(db)
        return
    seed_operational_data(db)
    seed_historical_incidents(db)
    sync_vector_memory(db)
