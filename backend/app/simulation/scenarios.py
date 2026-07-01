"""Scenario catalog for the Disaster Simulation Engine.

Each scenario maps a high-level failure ("AWS us-east-1 fails") to the set of
topology nodes that go down, a base downtime estimate, and the recovery
playbook template.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Set

from app.simulation.topology import Topology


@dataclass
class Scenario:
    key: str
    label: str
    description: str
    base_downtime_minutes: int
    recovery_strategy: List[str]
    # Given the topology + request params, returns the set of failed node ids.
    failed_nodes: Callable[[Topology, dict], Set[str]]
    severity: str = "high"


def _region_nodes(topo: Topology, region_id: str) -> Set[str]:
    """All infra primitives that go down when a region fails.

    Returns an EMPTY set when the region isn't in the topology, so the engine
    can detect an unknown target and report it instead of crashing or silently
    falling back to the default region.
    """
    if region_id not in topo.nodes:
        return set()
    target = topo.nodes[region_id]
    failed: Set[str] = {region_id}
    for node in topo.nodes.values():
        if (
            node.kind in {"cluster", "database", "ci"}
            and node.region == target.region
            and node.cloud == target.cloud
        ):
            failed.add(node.id)
    return failed


SCENARIOS: Dict[str, Scenario] = {
    "aws_region_outage": Scenario(
        key="aws_region_outage",
        label="AWS Region Outage",
        description="A full AWS region becomes unavailable.",
        base_downtime_minutes=45,
        severity="critical",
        recovery_strategy=[
            "Declare a SEV-1 and open an incident bridge.",
            "Promote the standby region (us-west-2) to primary.",
            "Fail over Postgres to the cross-region replica and verify RPO.",
            "Shift traffic via DNS/global load balancer to the healthy region.",
            "Validate checkout + payments golden paths before all-clear.",
        ],
        failed_nodes=lambda topo, p: _region_nodes(
            topo, p.get("target") or "aws:us-east-1"
        ),
    ),
    "azure_outage": Scenario(
        key="azure_outage",
        label="Azure Outage",
        description="An Azure region hosting ancillary services fails.",
        base_downtime_minutes=30,
        severity="high",
        recovery_strategy=[
            "Confirm only Azure-hosted services are affected.",
            "Re-route notification/analytics workloads to the AWS region.",
            "Queue async events for replay once Azure recovers.",
        ],
        failed_nodes=lambda topo, p: _region_nodes(
            topo, p.get("target") or "azure:eastus"
        ),
    ),
    "gcp_region_outage": Scenario(
        key="gcp_region_outage",
        label="GCP Region Outage",
        description="A GCP region (Cloud SQL / GCE) becomes unavailable.",
        base_downtime_minutes=40,
        severity="critical",
        recovery_strategy=[
            "Declare a SEV-1 and open an incident bridge.",
            "Fail Cloud SQL over to the standby region (us-central1) and verify RPO.",
            "Shift traffic via the global load balancer to the healthy region.",
            "Re-point services to the promoted Cloud SQL primary.",
            "Validate golden paths before all-clear.",
        ],
        failed_nodes=lambda topo, p: _region_nodes(
            topo, p.get("target") or "gcp:us-west1"
        ),
    ),
    "kubernetes_cluster_failure": Scenario(
        key="kubernetes_cluster_failure",
        label="Kubernetes Cluster Failure",
        description="The primary production K8s cluster loses quorum.",
        base_downtime_minutes=25,
        severity="critical",
        recovery_strategy=[
            "Cordon the failed cluster; stop the bleeding.",
            "Scale up the standby cluster (prod-west) and redeploy workloads.",
            "Repoint the gateway/service mesh to the healthy cluster.",
            "Run smoke tests on tier-0 services.",
        ],
        failed_nodes=lambda topo, p: {p.get("target") or "k8s:prod-east"},
    ),
    "database_failure": Scenario(
        key="database_failure",
        label="Database Failure",
        description="The primary Postgres instance fails.",
        base_downtime_minutes=20,
        severity="critical",
        recovery_strategy=[
            "Promote the read replica to primary.",
            "Repoint service connection strings / PgBouncer to the new primary.",
            "Verify data integrity and replication lag at cutover.",
            "Re-establish a new replica from the promoted primary.",
        ],
        failed_nodes=lambda topo, p: {p.get("target") or "postgres-primary"},
    ),
    "jenkins_failure": Scenario(
        key="jenkins_failure",
        label="Jenkins / CI Failure",
        description="The CI/CD system is down — no deploys or rollbacks via CI.",
        base_downtime_minutes=15,
        severity="medium",
        recovery_strategy=[
            "Running services are unaffected; deployments are blocked.",
            "Restore Jenkins from backup or stand up the warm spare controller.",
            "Use the break-glass manual deploy runbook for urgent rollbacks.",
        ],
        failed_nodes=lambda topo, p: {p.get("target") or "jenkins"},
    ),
    "deployment_rollback": Scenario(
        key="deployment_rollback",
        label="Deployment Rollback Scenario",
        description="A bad deploy must be rolled back across dependents.",
        base_downtime_minutes=10,
        severity="high",
        recovery_strategy=[
            "Roll the target service back to the last known-good version.",
            "Invalidate caches and warm them against the prior release.",
            "Verify dependent services recover; monitor error budgets.",
        ],
        failed_nodes=lambda topo, p: {p.get("target") or "checkout-service"},
    ),
    "cross_cloud_migration": Scenario(
        key="cross_cloud_migration",
        label="Cross-Cloud Migration",
        description="Evacuate AWS workloads to Azure (or vice-versa).",
        base_downtime_minutes=60,
        severity="high",
        recovery_strategy=[
            "Stand up the target-cloud landing zone and networking.",
            "Replicate data stores cross-cloud and validate consistency.",
            "Cut services over tier-by-tier (deepest dependencies first).",
            "Run full regression on tier-0 paths before decommissioning source.",
        ],
        failed_nodes=lambda topo, p: _region_nodes(
            topo, p.get("target") or "aws:us-east-1"
        ),
    ),
}


def get_scenario(key: str) -> Scenario:
    if key not in SCENARIOS:
        raise KeyError(
            f"unknown scenario {key!r}; valid: {', '.join(SCENARIOS)}"
        )
    return SCENARIOS[key]
