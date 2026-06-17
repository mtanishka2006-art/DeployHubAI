"""Builds the analysis context for the agent pipeline from the database."""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import (
    Backup,
    Deployment,
    FailoverEvent,
    Incident,
    InfrastructureMetric,
    ReplicationStatus,
)


def _row_to_dict(row, fields: List[str]) -> Dict[str, Any]:
    out = {}
    for f in fields:
        val = getattr(row, f, None)
        out[f] = val.isoformat() if hasattr(val, "isoformat") else val
    return out


def build_incident_context(
    db: Session,
    service: Optional[str] = None,
    environment: str = "prod",
    lookback_hours: int = 24,
    query: str = "",
) -> Dict[str, Any]:
    """Assemble metrics, logs, deployments and DR telemetry for the agents."""
    since = utcnow() - timedelta(hours=lookback_hours)

    metric_q = select(InfrastructureMetric).where(
        InfrastructureMetric.timestamp >= since
    )
    if service:
        metric_q = metric_q.where(InfrastructureMetric.service == service)
    metric_q = metric_q.order_by(InfrastructureMetric.timestamp).limit(500)
    metrics_rows = db.execute(metric_q).scalars().all()

    metrics, logs = [], []
    for m in metrics_rows:
        d = {
            "service": m.service,
            "metric_name": m.metric_name,
            "value": m.value,
            "unit": m.unit,
            "severity": "info",
            "timestamp": m.timestamp.isoformat(),
        }
        if m.metric_name in {"log_event", "log"}:
            logs.append({**d, "severity": (m.meta or {}).get("level", "info")})
        else:
            metrics.append(d)

    # Recent error incidents act as the "logs" signal for RCA too.
    inc_q = select(Incident).where(Incident.detected_at >= since)
    if service:
        inc_q = inc_q.where(Incident.service == service)
    for inc in db.execute(inc_q.limit(100)).scalars().all():
        logs.append(
            {
                "service": inc.service,
                "severity": inc.severity,
                "message": inc.description,
                "error_signature": inc.title,
                "timestamp": inc.detected_at.isoformat(),
            }
        )

    dep_q = select(Deployment).order_by(Deployment.timestamp.desc())
    if service:
        dep_q = dep_q.where(Deployment.service == service)
    deployments = [
        _row_to_dict(
            d, ["service", "environment", "version", "status", "actor", "timestamp"]
        )
        for d in db.execute(dep_q.limit(20)).scalars().all()
    ]

    backups = [
        _row_to_dict(b, ["system", "service", "status", "last_backup", "rpo_minutes"])
        for b in db.execute(select(Backup).limit(50)).scalars().all()
    ]
    replication = [
        _row_to_dict(r, ["source", "target", "status", "lag_seconds"])
        for r in db.execute(select(ReplicationStatus).limit(50)).scalars().all()
    ]
    failovers = [
        _row_to_dict(f, ["service", "region", "status", "last_tested", "rto_minutes"])
        for f in db.execute(select(FailoverEvent).limit(50)).scalars().all()
    ]

    return {
        "service": service or "platform",
        "environment": environment,
        "query": query or service or "incident",
        "metrics": metrics,
        "logs": logs,
        "deployments": deployments,
        "backups": backups,
        "replication": replication,
        "failovers": failovers,
    }
