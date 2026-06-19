"""Disaster Simulation Engine.

Given a scenario, it:
  1. Traces dependencies through the topology graph
  2. Identifies affected services
  3. Predicts blast radius
  4. Estimates downtime
  5. Suggests a recovery strategy
  6. Suggests a failover sequence

Results are persisted as SimulationReport rows and (optionally) published to the
`simulation-events` Kafka topic.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import SimulationReport
from app.messaging.event_bus import get_event_bus
from app.messaging.topics import SIMULATION_EVENTS
from app.schemas.events import EventType, UnifiedEvent
from app.simulation.scenarios import Scenario, get_scenario
from app.simulation.topology import (
    Topology,
    default_topology,
    topology_from_services,
)

logger = get_logger("simulation")

_IMPACT_BY_TIER = {0: "critical", 1: "high", 2: "moderate", 3: "low"}


def build_topology(db: Optional[Session]) -> Topology:
    """Reflect the imported/connected app's services when one exists; otherwise
    fall back to the static demo topology.

    This is what makes the Simulation Center mirror the connected project: its
    services become the simulation's services, mapped onto the standard infra
    skeleton so the region/cluster/DB/CI scenarios still apply.
    """
    if db is not None:
        try:
            from sqlalchemy import func, select

            from app.db.models import ConnectedApp, InfrastructureMetric

            if db.scalar(select(func.count(ConnectedApp.id))):
                services = [
                    s
                    for s in db.execute(
                        select(InfrastructureMetric.service).distinct()
                    ).scalars().all()
                    if s
                ]
                if services:
                    return topology_from_services(services)
        except Exception:  # noqa: BLE001 - never let topology building crash a run
            logger.debug("dynamic topology build failed; using default")
    return default_topology()


def valid_targets(scenario_type: str, topo: Topology):
    """Return (param_name, [allowed values]) a user may target for a scenario.

    Used both to validate input and to populate the dashboard's dropdown so the
    user can only pick targets that actually exist in the topology.
    """
    def regions(cloud: str):
        return sorted(
            {n.region for n in topo.nodes.values()
             if n.kind == "region" and n.cloud == cloud and n.region}
        )

    def ids(kind: str):
        return sorted(n.id for n in topo.nodes.values() if n.kind == kind)

    if scenario_type in ("aws_region_outage", "cross_cloud_migration"):
        return "region", regions("aws")
    if scenario_type == "azure_outage":
        return "region", regions("azure")
    if scenario_type == "kubernetes_cluster_failure":
        return "target", ids("cluster")
    if scenario_type == "database_failure":
        return "target", ids("database")
    if scenario_type == "jenkins_failure":
        return "target", ids("ci")
    if scenario_type == "deployment_rollback":
        return "target", sorted(n.id for n in topo.services())
    return "target", []


class SimulationEngine:
    def __init__(self, db: Optional[Session] = None, topology: Optional[Topology] = None):
        self.db = db
        self.topo = topology or build_topology(db)

    def run(
        self, scenario_type: str, target: Optional[str] = None,
        region: Optional[str] = None, params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        scenario = get_scenario(scenario_type)
        params = dict(params or {})
        explicit = target or region  # what the user actually asked for
        if target:
            params["target"] = target
        elif region:
            params["target"] = self._region_to_node(region)

        failed = scenario.failed_nodes(self.topo, params)
        failed = {n for n in failed if n in self.topo.nodes}
        if not failed:
            if explicit:
                # The user picked a target the topology doesn't know about —
                # tell them instead of silently simulating the default.
                param, options = valid_targets(scenario_type, self.topo)
                raise ValueError(
                    f"'{explicit}' is not a valid {param} for "
                    f"'{scenario.label}'. Valid options: "
                    f"{', '.join(options) or 'none configured'}."
                )
            # No explicit target: use the scenario's default failure set.
            failed = {
                n for n in scenario.failed_nodes(self.topo, {})
                if n in self.topo.nodes
            }

        if not failed:
            # The scenario's hardcoded default target (e.g. "checkout-service")
            # isn't present in an import-derived topology — fall back to the most
            # critical service so the simulation still produces a result.
            svc_nodes = sorted(self.topo.services(), key=lambda n: n.tier)
            if svc_nodes:
                failed = {svc_nodes[0].id}

        impacted = self.topo.impacted_by(failed)  # (node, hop)
        affected_services = self._affected_services(failed, impacted)
        blast = self._blast_radius(affected_services, failed)
        downtime = self._downtime(scenario, affected_services, failed)
        failover_seq = self._failover_sequence(scenario, failed, affected_services)
        dep_trace = self.topo.trace_edges(failed, {n for n, _ in impacted})
        summary = self._summary(scenario, failed, affected_services, downtime)

        report = {
            "scenario_type": scenario_type,
            "summary": summary,
            "affected_services": affected_services,
            "blast_radius": blast,
            "estimated_downtime_minutes": downtime,
            "recovery_strategy": scenario.recovery_strategy,
            "failover_sequence": failover_seq,
            "dependency_trace": dep_trace,
        }
        self._persist_and_publish(report, target or params.get("target", ""), region)
        return report

    # ------------------------------------------------------------------ #
    def _affected_services(
        self, failed: Set[str], impacted: List
    ) -> List[Dict[str, Any]]:
        services: List[Dict[str, Any]] = []
        # Directly failed services.
        for nid in failed:
            node = self.topo.nodes[nid]
            if node.kind == "service":
                services.append(
                    {"service": nid, "impact": "critical", "environment": "prod"}
                )
        # Indirectly impacted services, by dependency hop + tier.
        for nid, hop in impacted:
            node = self.topo.nodes.get(nid)
            if node and node.kind == "service":
                impact = _IMPACT_BY_TIER.get(node.tier, "moderate")
                if hop >= 3 and impact == "moderate":
                    impact = "low"
                services.append(
                    {"service": nid, "impact": impact, "environment": "prod"}
                )
        # De-dup keeping the most severe impact.
        order = {"critical": 0, "high": 1, "moderate": 2, "low": 3}
        best: Dict[str, Dict[str, Any]] = {}
        for s in services:
            cur = best.get(s["service"])
            if cur is None or order[s["impact"]] < order[cur["impact"]]:
                best[s["service"]] = s
        return sorted(best.values(), key=lambda s: order[s["impact"]])

    def _blast_radius(self, services: List[Dict[str, Any]], failed: Set[str]) -> Dict:
        total_services = len(self.topo.services())
        count = len(services)
        critical = sum(1 for s in services if s["impact"] == "critical")
        pct = (count / total_services * 100) if total_services else 0
        if critical >= 2 or pct >= 60:
            severity = "critical"
        elif pct >= 30:
            severity = "high"
        elif pct > 0:
            severity = "moderate"
        else:
            severity = "low"
        infra = sorted(n for n in failed if self.topo.nodes[n].kind != "service")
        return {
            "service_count": count,
            "severity": severity,
            "description": (
                f"{count}/{total_services} services impacted "
                f"({pct:.0f}% of the fleet); {critical} critical. "
                f"Failed infrastructure: {', '.join(infra) or 'n/a'}."
            ),
        }

    def _downtime(self, scenario: Scenario, services, failed: Set[str]) -> int:
        downtime = scenario.base_downtime_minutes
        # Each impacted critical service adds recovery overhead.
        downtime += 5 * sum(1 for s in services if s["impact"] == "critical")
        # If a failover target exists for the failed primitives, cut downtime.
        if any(self.topo.nodes[n].failover for n in failed):
            downtime = int(downtime * 0.6)
        return max(5, downtime)

    def _failover_sequence(
        self, scenario: Scenario, failed: Set[str], services
    ) -> List[Dict[str, Any]]:
        steps: List[Dict[str, Any]] = []
        step = 1

        # 1. Failover any infra primitive that has a standby.
        for nid in sorted(failed):
            node = self.topo.nodes[nid]
            if node.failover:
                steps.append(
                    {
                        "step": step,
                        "action": f"Fail over {nid} → {node.failover}",
                        "eta_minutes": 8 if node.kind == "database" else 12,
                    }
                )
                step += 1

        # 2. Recover services deepest-tier first (highest tier number first),
        #    so dependencies are healthy before dependents.
        svc_nodes = sorted(
            (self.topo.nodes[s["service"]] for s in services),
            key=lambda n: -n.tier,
        )
        for node in svc_nodes:
            steps.append(
                {
                    "step": step,
                    "action": f"Recover & health-check {node.id} "
                    f"(tier {node.tier})",
                    "eta_minutes": 3 + node.tier,
                }
            )
            step += 1

        if not steps:
            steps.append(
                {"step": 1, "action": "No automated failover path; manual recovery.",
                 "eta_minutes": scenario.base_downtime_minutes}
            )
        return steps

    def _summary(self, scenario: Scenario, failed, services, downtime: int) -> str:
        return (
            f"Simulating '{scenario.label}': {scenario.description} "
            f"Failure of {', '.join(sorted(failed))} would impact "
            f"{len(services)} service(s) with an estimated "
            f"{downtime} minute recovery window."
        )

    @staticmethod
    def _region_to_node(region: str) -> str:
        mapping = {
            "us-east-1": "aws:us-east-1",
            "us-west-2": "aws:us-west-2",
            "eastus": "azure:eastus",
        }
        return mapping.get(region, region)

    def _persist_and_publish(self, report: Dict[str, Any], target: str, region) -> None:
        if self.db is not None:
            row = SimulationReport(
                scenario_type=report["scenario_type"],
                target=target or "",
                region=region or "",
                summary=report["summary"],
                affected_services=report["affected_services"],
                blast_radius=report["blast_radius"],
                estimated_downtime_minutes=report["estimated_downtime_minutes"],
                recovery_strategy=report["recovery_strategy"],
                failover_sequence=report["failover_sequence"],
                dependency_trace=report["dependency_trace"],
            )
            self.db.add(row)
            self.db.commit()
        try:
            get_event_bus().publish(
                SIMULATION_EVENTS,
                UnifiedEvent(
                    source="simulation",
                    event_type=EventType.DR_EVENT.value,
                    severity=report["blast_radius"]["severity"],
                    service=target or report["scenario_type"],
                    metadata={"summary": report["summary"]},
                ),
            )
        except Exception:  # noqa: BLE001
            logger.debug("simulation event publish skipped")
