"""Disaster Recovery Agent — DR readiness scoring + recovery risk assessment.

Inputs : backup status, replication status, failover status.
Output : {"dr_score": int, "readiness": str, ...}
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.agents.base import BaseAgent


def _hours_since(ts: Any) -> float:
    if not ts:
        return 9999.0
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            return 9999.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0


class DisasterRecoveryAgent(BaseAgent):
    name = "disaster_recovery"

    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        backups: List[Dict[str, Any]] = context.get("backups", [])
        replication: List[Dict[str, Any]] = context.get("replication", [])
        failovers: List[Dict[str, Any]] = context.get("failovers", [])

        backup_score, backup_risks = self._score_backups(backups)
        repl_score, repl_risks = self._score_replication(replication)
        failover_score, failover_risks = self._score_failovers(failovers)

        # Weighted composite (backups 35%, replication 30%, failover 35%).
        dr_score = round(
            0.35 * backup_score + 0.30 * repl_score + 0.35 * failover_score
        )
        risks = backup_risks + repl_risks + failover_risks
        readiness = self._readiness(dr_score)
        confidence = round(
            min(0.97, 0.5 + 0.05 * (len(backups) + len(replication) + len(failovers))),
            2,
        )
        return {
            "dr_score": dr_score,
            "readiness": readiness,
            "confidence": confidence,
            "components": {
                "backups": backup_score,
                "replication": repl_score,
                "failover": failover_score,
            },
            "risks": risks,
        }

    def _score_backups(self, backups):
        if not backups:
            return 40, ["No backup systems reporting — recovery point unknown."]
        score, risks = 100, []
        for b in backups:
            if b.get("status") not in {"healthy", "ok", "success"}:
                score -= 25
                risks.append(f"Backup {b.get('system')} status={b.get('status')}")
            if _hours_since(b.get("last_backup")) > (b.get("rpo_minutes", 60) / 60.0) * 2:
                score -= 15
                risks.append(f"Backup {b.get('system')} stale vs RPO")
        return max(0, score), risks

    def _score_replication(self, replication):
        if not replication:
            return 50, ["No replication telemetry available."]
        score, risks = 100, []
        for r in replication:
            if r.get("status") not in {"in_sync", "healthy"}:
                score -= 30
                risks.append(f"Replication {r.get('source')}→{r.get('target')} "
                             f"{r.get('status')}")
            if int(r.get("lag_seconds", 0)) > 300:
                score -= 20
                risks.append(f"Replication lag {r.get('lag_seconds')}s "
                             f"({r.get('source')})")
        return max(0, score), risks

    def _score_failovers(self, failovers):
        if not failovers:
            return 45, ["No failover configuration detected."]
        score, risks = 100, []
        for f in failovers:
            if f.get("status") not in {"ready", "healthy", "active"}:
                score -= 30
                risks.append(f"Failover for {f.get('service')} not ready "
                             f"({f.get('status')})")
            if _hours_since(f.get("last_tested")) > 24 * 90:  # untested in 90d
                score -= 15
                risks.append(f"Failover for {f.get('service')} untested >90d")
        return max(0, score), risks

    @staticmethod
    def _readiness(score: int) -> str:
        if score >= 85:
            return "ready"
        if score >= 65:
            return "partial"
        if score >= 40:
            return "at_risk"
        return "not_ready"


# --------------------------------------------------------------------------- #
# Website DR — computed from REAL externally-observable signals, no fabrication.
# --------------------------------------------------------------------------- #
def score_website_resilience(
    tls_valid: bool, cert_days: Optional[float],
    redundancy: Optional[float], uptime_pct: Optional[float],
):
    """Score a live website's disaster-readiness from measured facts only:
    TLS certificate health, DNS endpoint redundancy, and observed uptime.
    Returns (score, components)."""
    # TLS pillar — a broken or expiring certificate is a real outage risk.
    if not tls_valid:
        tls = 30.0
    elif cert_days is None or cert_days < 0:
        tls = 70.0
    elif cert_days < 7:
        tls = 40.0
    elif cert_days < 30:
        tls = 75.0
    else:
        tls = 100.0

    # Redundancy pillar — distinct resolved IPs == real failover capacity.
    if not redundancy or redundancy <= 0:
        red = 50.0
    elif redundancy >= 3:
        red = 100.0
    elif redundancy >= 2:
        red = 75.0
    else:
        red = 35.0  # single IP => single point of failure

    up = 100.0 if uptime_pct is None else max(0.0, min(100.0, float(uptime_pct)))
    score = round(0.30 * tls + 0.30 * red + 0.40 * up)
    return score, {"tls": round(tls), "redundancy": round(red), "uptime": round(up)}


def website_dr_from_metrics(db) -> Optional[Dict[str, Any]]:
    """DR readiness for a connected website, from the REAL signals its probes
    recorded (TLS validity/expiry, DNS redundancy, measured uptime). Returns
    None when there is no website telemetry to score."""
    from sqlalchemy import func, select

    from app.db.models import ConnectedApp, InfrastructureMetric

    has_site = db.scalar(
        select(func.count(ConnectedApp.id)).where(
            ConnectedApp.app_type == "website"
        )
    )
    if not has_site:
        return None

    def _latest(metric_name: str):
        return db.execute(
            select(InfrastructureMetric.value)
            .where(
                InfrastructureMetric.source == "website",
                InfrastructureMetric.metric_name == metric_name,
            )
            .order_by(InfrastructureMetric.timestamp.desc())
            .limit(1)
        ).scalar()

    tls_valid = _latest("tls_valid")
    cert_days = _latest("cert_days_to_expiry")
    redundancy = _latest("endpoint_redundancy")
    uptime = db.scalar(
        select(func.avg(InfrastructureMetric.value)).where(
            InfrastructureMetric.source == "website",
            InfrastructureMetric.metric_name == "availability",
        )
    )
    if tls_valid is None and redundancy is None and uptime is None:
        return None

    score, components = score_website_resilience(
        bool(tls_valid) if tls_valid is not None else False,
        cert_days, redundancy, uptime,
    )
    return {
        "dr_score": score,
        "readiness": DisasterRecoveryAgent._readiness(score),
        "components": components,
        "kind": "website",
    }
