"""Mission Control Center — the orchestration brain.

Implements the spec workflow:

    receive incident -> Monitoring -> RCA -> DR -> query Memory ->
    Recovery -> aggregate -> Unified Incident Report

Built on LangGraph when available (a real StateGraph wiring the agent nodes).
If LangGraph isn't installed it transparently degrades to an equivalent
sequential engine, so the orchestration always runs.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.agents.dr_agent import DisasterRecoveryAgent
from app.agents.monitoring_agent import MonitoringAgent
from app.agents.rca_agent import RCAAgent
from app.agents.recovery_agent import RecoveryAgent
from app.core.logging import get_logger
from app.db.models import Incident, MissionControlReport, RecoveryAction
from app.memory.infrastructure_memory import get_memory
from app.mission_control.context import build_incident_context
from app.mission_control.state import MissionState

logger = get_logger("mission_control")


class MissionControl:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.monitoring = MonitoringAgent(db)
        self.rca = RCAAgent(db)
        self.dr = DisasterRecoveryAgent(db)
        self.recovery = RecoveryAgent(db)
        self.memory = get_memory()
        self._graph = self._build_graph()

    # ------------------------------------------------------------------ #
    # Workflow nodes (shared by both LangGraph and the fallback engine)
    # ------------------------------------------------------------------ #
    def node_gather(self, state: MissionState) -> MissionState:
        state["context"] = build_incident_context(
            self.db,
            service=state.get("service"),
            environment=state.get("environment", "prod"),
            query=state.get("query", ""),
        )
        return state

    def node_monitoring(self, state: MissionState) -> MissionState:
        out = self.monitoring.analyze(state["context"])
        self.monitoring.persist(out, state.get("incident_id"))
        state["monitoring"] = out
        return state

    def node_rca(self, state: MissionState) -> MissionState:
        ctx = {**state["context"], "anomalies": state["monitoring"].get("anomalies", [])}
        out = self.rca.analyze(ctx)
        self.rca.persist(out, state.get("incident_id"))
        state["rca"] = out
        return state

    def node_dr(self, state: MissionState) -> MissionState:
        out = self.dr.analyze(state["context"])
        self.dr.persist(out, state.get("incident_id"))
        state["dr"] = out
        return state

    def node_memory(self, state: MissionState) -> MissionState:
        query = state["rca"].get("root_cause") or state.get("query", "")
        state["similar_incidents"] = self.memory.search_similar_incidents(query, k=5)
        return state

    def node_recovery(self, state: MissionState) -> MissionState:
        ctx = {
            "service": state.get("service", "platform"),
            "rca": state["rca"],
            "dr": state["dr"],
            "similar_incidents": state.get("similar_incidents", []),
        }
        out = self.recovery.analyze(ctx)
        self.recovery.persist(out, state.get("incident_id"))
        state["recovery"] = out
        return state

    def node_aggregate(self, state: MissionState) -> MissionState:
        state["report"] = self._aggregate(state)
        return state

    # ------------------------------------------------------------------ #
    # Graph construction (LangGraph) with sequential fallback
    # ------------------------------------------------------------------ #
    def _build_graph(self):
        try:
            from langgraph.graph import END, START, StateGraph

            g = StateGraph(MissionState)
            g.add_node("gather", self.node_gather)
            g.add_node("monitoring", self.node_monitoring)
            g.add_node("rca", self.node_rca)
            g.add_node("dr", self.node_dr)
            g.add_node("memory", self.node_memory)
            g.add_node("recovery", self.node_recovery)
            g.add_node("aggregate", self.node_aggregate)

            g.add_edge(START, "gather")
            g.add_edge("gather", "monitoring")
            g.add_edge("monitoring", "rca")
            g.add_edge("rca", "dr")
            g.add_edge("dr", "memory")
            g.add_edge("memory", "recovery")
            g.add_edge("recovery", "aggregate")
            g.add_edge("aggregate", END)
            logger.info("Mission Control using LangGraph StateGraph")
            return g.compile()
        except Exception as exc:  # noqa: BLE001
            logger.warning("LangGraph unavailable (%s); using sequential engine", exc)
            return None

    def run(self, request: Dict[str, Any]) -> Dict[str, Any]:
        incident = self._resolve_incident(request)
        state: MissionState = {
            "incident_id": incident.id if incident else None,
            "service": request.get("service")
            or (incident.service if incident else "platform"),
            "environment": request.get("environment", "prod"),
            "severity": request.get("severity", "high"),
            "query": request.get("description")
            or (incident.title if incident else request.get("service", "incident")),
        }

        if self._graph is not None:
            final = self._graph.invoke(state)
        else:
            for node in (
                self.node_gather,
                self.node_monitoring,
                self.node_rca,
                self.node_dr,
                self.node_memory,
                self.node_recovery,
                self.node_aggregate,
            ):
                state = node(state)
            final = state

        report = final["report"]
        self._persist(final, incident)
        return report

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _resolve_incident(self, request: Dict[str, Any]) -> Optional[Incident]:
        inc_id = request.get("incident_id")
        if inc_id:
            return self.db.get(Incident, inc_id)
        if request.get("description"):
            inc = Incident(
                title=request["description"][:120],
                description=request["description"],
                severity=request.get("severity", "high"),
                service=request.get("service", "platform"),
                environment=request.get("environment", "prod"),
                source="mission_control",
                status="investigating",
            )
            self.db.add(inc)
            self.db.flush()
            return inc
        return None

    def _aggregate(self, state: MissionState) -> Dict[str, Any]:
        mon, rca, dr = state["monitoring"], state["rca"], state["dr"]
        rec = state["recovery"]
        summary = self._executive_summary(state)
        return {
            "incident_id": state.get("incident_id"),
            "severity": self._compute_severity(state),
            "system_health": mon.get("health_status", "unknown"),
            "root_cause": rca.get("root_cause", "unknown"),
            "dr_readiness": dr.get("readiness", "unknown"),
            "similar_incidents": [
                {
                    "title": s.get("title"),
                    "score": s.get("score"),
                    "root_cause": s.get("root_cause"),
                }
                for s in state.get("similar_incidents", [])
            ],
            "recommended_actions": rec.get("recommendations", []),
            "executive_summary": summary,
            "monitoring": mon,
            "rca": rca,
            "dr": dr,
            "recovery": rec,
        }

    def _compute_severity(self, state: MissionState) -> str:
        """Derive incident severity from the agents' evidence.

        This is what makes Mission Control *decide* severity instead of asking
        the user: it blends the monitoring health score, the RCA signal, and DR
        readiness into a single critical/high/medium/low rating.
        """
        mon, rca, dr = state["monitoring"], state["rca"], state["dr"]
        score = int(mon.get("health_score", 100) or 100)
        health = mon.get("health_status", "healthy")
        root_cause = (rca.get("root_cause") or "").lower()
        dr_ready = dr.get("readiness", "ready")

        # 1. Base severity on system health.
        if health == "critical" or score < 35:
            severity = "critical"
        elif health == "unhealthy" or score < 60:
            severity = "high"
        elif health == "degraded" or score < 85:
            severity = "medium"
        else:
            severity = "low"

        # A genuinely healthy service is not an active incident — don't let
        # global DR concerns or speculative RCA hypotheses escalate it.
        if severity == "low":
            return "low"

        rank = ["low", "medium", "high", "critical"]

        # 2. Escalate when a deployment clearly broke production (only meaningful
        #    once the service is already showing impact).
        deploy_caused = (
            "failed deployment" in root_cause or "rolled_back" in root_cause
        )
        if deploy_caused and severity in {"medium", "high"}:
            severity = rank[min(rank.index(severity) + 1, 3)]

        # 3. Escalate when disaster recovery cannot safely absorb the impact.
        if dr_ready in {"at_risk", "not_ready"} and severity in {"high", "medium"}:
            severity = rank[min(rank.index(severity) + 1, 3)]

        return severity

    def _executive_summary(self, state: MissionState) -> str:
        mon, rca, dr, rec = (
            state["monitoring"],
            state["rca"],
            state["dr"],
            state["recovery"],
        )
        top_action = (
            rec.get("recommendations", [{}])[0].get("action", "engage on-call")
            if rec.get("recommendations")
            else "engage on-call"
        )
        heuristic = (
            f"System health is {mon.get('health_status', 'unknown')} "
            f"(score {mon.get('health_score', 'n/a')}). "
            f"Most likely root cause: {rca.get('root_cause', 'unknown')} "
            f"(confidence {rca.get('confidence', 0):.0%}). "
            f"DR readiness is {dr.get('readiness', 'unknown')} "
            f"(score {dr.get('dr_score', 0)}). "
            f"Recommended first action: {top_action}."
        )
        # Optionally upgrade the prose with an LLM, falling back to heuristic.
        llm = self.recovery.llm
        if llm.available:
            prompt = (
                "Write a concise 3-4 sentence executive incident summary for "
                "leadership based on this analysis JSON. Be specific and calm.\n\n"
                f"Monitoring: {mon}\nRCA: {rca}\nDR: {dr}\nRecovery: {rec}"
            )
            generated = llm.complete(prompt, system="You are a principal SRE.")
            if generated:
                return generated
        return heuristic

    def _persist(self, state: MissionState, incident: Optional[Incident]) -> None:
        report = state["report"]
        row = MissionControlReport(
            incident_id=state.get("incident_id"),
            system_health=report["system_health"],
            root_cause=report["root_cause"],
            dr_readiness=report["dr_readiness"],
            similar_incidents=report["similar_incidents"],
            recommended_actions=report["recommended_actions"],
            executive_summary=report["executive_summary"],
            raw_outputs={
                "severity": report["severity"],
                "monitoring": state["monitoring"],
                "rca": state["rca"],
                "dr": state["dr"],
                "recovery": state["recovery"],
            },
        )
        self.db.add(row)

        # Materialize recommended actions + update incident root cause and the
        # AI-computed severity (overriding any placeholder the ticket had).
        if incident:
            incident.root_cause = report["root_cause"]
            incident.severity = report["severity"]
            if incident.status == "open":
                incident.status = "investigating"
            for r in report["recommended_actions"]:
                self.db.add(
                    RecoveryAction(
                        incident_id=incident.id,
                        action=r.get("action", ""),
                        rationale=r.get("rationale", ""),
                        risk=r.get("risk", "low"),
                        priority=int(r.get("priority", 1)),
                    )
                )
        self.db.commit()
