"""Overview dashboard aggregate route."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.dr_agent import DisasterRecoveryAgent, website_dr_from_metrics
from app.agents.monitoring_agent import MonitoringAgent
from app.api.deps import get_current_user
from app.db.base import utcnow
from app.db.models import (
    Backup,
    Deployment,
    FailoverEvent,
    Incident,
    InfrastructureMetric,
    ReplicationStatus,
    User,
)
from app.db.session import get_db
from app.schemas.api import (
    DRReadiness,
    HealthByService,
    OverviewResponse,
    SystemHealth,
)

router = APIRouter(tags=["overview"])


@router.get("/services", response_model=list[str])
def services(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Distinct services currently present in the platform's data — used to
    populate service pickers so they reflect the connected/imported app."""
    names: set[str] = set()
    for column in (
        InfrastructureMetric.service,
        Deployment.service,
        Incident.service,
    ):
        for (name,) in db.execute(select(column).distinct()).all():
            if name:
                names.add(name)
    return sorted(names)


@router.get("/overview", response_model=OverviewResponse)
def overview(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    since = utcnow() - timedelta(hours=24)

    # Active incidents.
    active = db.scalar(
        select(func.count(Incident.id)).where(
            Incident.status.in_(["open", "investigating", "mitigated"])
        )
    ) or 0

    # Recovery success rate from resolved incidents in the window.
    resolved = db.scalar(
        select(func.count(Incident.id)).where(Incident.status == "resolved")
    ) or 0
    total_closed = resolved + (
        db.scalar(
            select(func.count(Incident.id)).where(Incident.status == "mitigated")
        ) or 0
    )
    recovery_rate = round((resolved / total_closed * 100) if total_closed else 100.0, 1)

    # Per-service health via the monitoring agent over recent metrics.
    services = [
        row[0]
        for row in db.execute(
            select(InfrastructureMetric.service).distinct().limit(12)
        ).all()
    ]
    # Which connector app_types have fed each service (for live-data badges).
    from app.db.models import ConnectorEvent

    connector_map: dict[str, set] = {}
    for svc, app_type in db.execute(
        select(ConnectorEvent.service, ConnectorEvent.app_type).distinct()
    ).all():
        connector_map.setdefault(svc, set()).add(app_type)

    mon = MonitoringAgent(db)
    health_by_service = []
    overall_scores = []
    for svc in services:
        metrics = [
            {"service": m.service, "metric_name": m.metric_name, "value": m.value}
            for m in db.execute(
                select(InfrastructureMetric)
                .where(
                    InfrastructureMetric.service == svc,
                    InfrastructureMetric.timestamp >= since,
                )
                .limit(100)
            ).scalars().all()
        ]
        result = mon.analyze({"metrics": metrics, "logs": []})
        score = result["health_score"]
        overall_scores.append(score)
        health_by_service.append(
            HealthByService(
                service=svc,
                score=score,
                status=result["health_status"],
                connectors=sorted(connector_map.get(svc, set())),
            )
        )

    overall = round(sum(overall_scores) / len(overall_scores)) if overall_scores else 92
    system_health = SystemHealth(
        status=mon._status_from_score(overall), score=overall
    )

    # DR readiness.
    backup_rows = db.execute(select(Backup)).scalars().all()
    repl_rows = db.execute(select(ReplicationStatus)).scalars().all()
    failover_rows = db.execute(select(FailoverEvent)).scalars().all()

    web_dr = None
    if not backup_rows and not repl_rows and not failover_rows:
        # No infra DR telemetry — score a connected website from its real
        # measured resilience signals (TLS, DNS redundancy, uptime).
        web_dr = website_dr_from_metrics(db)

    if web_dr is not None:
        dr = web_dr
    else:
        dr_agent = DisasterRecoveryAgent(db)
        dr = dr_agent.analyze(
            {
                "backups": [
                    {"system": b.system, "status": b.status,
                     "last_backup": b.last_backup.isoformat(),
                     "rpo_minutes": b.rpo_minutes}
                    for b in backup_rows
                ],
                "replication": [
                    {"source": r.source, "target": r.target, "status": r.status,
                     "lag_seconds": r.lag_seconds}
                    for r in repl_rows
                ],
                "failovers": [
                    {"service": f.service, "status": f.status,
                     "last_tested": f.last_tested.isoformat() if f.last_tested else None}
                    for f in failover_rows
                ],
            }
        )

    recent_deployments = db.execute(
        select(Deployment).order_by(Deployment.timestamp.desc()).limit(8)
    ).scalars().all()

    timeline_rows = db.execute(
        select(Incident).order_by(Incident.detected_at.desc()).limit(12)
    ).scalars().all()
    incident_timeline = [
        {
            "id": i.id,
            "title": i.title,
            "severity": i.severity,
            "status": i.status,
            "service": i.service,
            "timestamp": i.detected_at.isoformat(),
        }
        for i in timeline_rows
    ]

    return OverviewResponse(
        system_health=system_health,
        active_incidents=active,
        recovery_success_rate=recovery_rate,
        dr_readiness=DRReadiness(score=dr["dr_score"], readiness=dr["readiness"]),
        recent_deployments=recent_deployments,
        incident_timeline=incident_timeline,
        health_by_service=health_by_service,
    )
