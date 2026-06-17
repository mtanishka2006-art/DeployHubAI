"""Disaster Recovery Agent — DR readiness scoring + recovery risk assessment.

Inputs : backup status, replication status, failover status.
Output : {"dr_score": int, "readiness": str, ...}
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

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
