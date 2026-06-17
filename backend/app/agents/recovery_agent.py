"""Recovery Agent — recommends recovery actions, rollback + failover strategy.

Inputs : RCA result, retrieved historical incidents, DR assessment.
Output : {"recommendations": [...], "confidence": float, ...}
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.agents.base import BaseAgent


class RecoveryAgent(BaseAgent):
    name = "recovery"

    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        rca: Dict[str, Any] = context.get("rca", {})
        dr: Dict[str, Any] = context.get("dr", {})
        history: List[Dict[str, Any]] = context.get("similar_incidents", [])
        service = context.get("service", "the affected service")

        root_cause = (rca.get("root_cause") or "").lower()
        recommendations: List[Dict[str, Any]] = []

        # 1. Cause-driven primary action.
        if "deployment" in root_cause or "regression" in root_cause:
            recommendations.append(
                self._rec(
                    f"Roll back {service} to the last known-good release",
                    "RCA attributes the incident to a recent deployment; rollback "
                    "is the fastest path to restore service.",
                    risk="low",
                    priority=1,
                )
            )
            recommendations.append(
                self._rec(
                    "Freeze the deployment pipeline until a fix is verified",
                    "Prevents the same regression from being re-applied.",
                    risk="low",
                    priority=2,
                )
            )
        if "saturation" in root_cause or "cpu" in root_cause or "memory" in root_cause:
            recommendations.append(
                self._rec(
                    f"Scale out {service} (increase replicas / instance size)",
                    "Resource saturation detected; horizontal scaling relieves "
                    "pressure while the root cause is addressed.",
                    risk="low",
                    priority=1,
                )
            )
        if "replication" in root_cause or "backup" in root_cause:
            recommendations.append(
                self._rec(
                    "Re-establish replication and verify backup integrity",
                    "Data-protection subsystem is implicated.",
                    risk="medium",
                    priority=1,
                )
            )

        # 2. DR-driven failover guidance.
        dr_score = int(dr.get("dr_score", 0) or 0)
        if dr.get("readiness") in {"ready", "partial"} and dr_score >= 60:
            recommendations.append(
                self._rec(
                    "Initiate regional failover to the standby site",
                    f"DR readiness is {dr.get('readiness')} (score {dr_score}); "
                    "failover is viable and limits customer impact.",
                    risk="medium",
                    priority=2,
                )
            )
        else:
            recommendations.append(
                self._rec(
                    "Do NOT fail over yet — remediate DR gaps first",
                    f"DR readiness is {dr.get('readiness', 'unknown')} "
                    f"(score {dr_score}); failover risks data loss.",
                    risk="high",
                    priority=3,
                )
            )

        # 3. Learn from history — promote actions that worked before.
        for hit in history[:2]:
            for action in (hit.get("recovery_actions") or [])[:2]:
                recommendations.append(
                    self._rec(
                        action,
                        f"Resolved a similar past incident "
                        f"(similarity {hit.get('score', 0):.2f}).",
                        risk="low",
                        priority=2,
                    )
                )

        if not recommendations:
            recommendations.append(
                self._rec(
                    "Engage on-call SRE and open a war room",
                    "Automated analysis is inconclusive; escalate to humans.",
                    risk="low",
                    priority=1,
                )
            )

        # De-duplicate by action text, keep highest priority (lowest number).
        deduped: Dict[str, Dict[str, Any]] = {}
        for r in recommendations:
            key = r["action"]
            if key not in deduped or r["priority"] < deduped[key]["priority"]:
                deduped[key] = r
        ordered = sorted(deduped.values(), key=lambda r: r["priority"])

        rollback = any("roll back" in r["action"].lower() for r in ordered)
        failover = any("failover" in r["action"].lower() for r in ordered)
        confidence = round(
            min(0.95, 0.5 + 0.1 * len(ordered) + 0.2 * float(rca.get("confidence", 0))),
            2,
        )
        return {
            "recommendations": ordered,
            "rollback_recommended": rollback,
            "failover_recommended": failover,
            "confidence": confidence,
        }

    @staticmethod
    def _rec(action: str, rationale: str, risk: str, priority: int) -> Dict[str, Any]:
        return {
            "action": action,
            "rationale": rationale,
            "risk": risk,
            "priority": priority,
        }
