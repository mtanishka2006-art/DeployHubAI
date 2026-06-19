"""Infrastructure dependency topology.

A directed graph of services and the infrastructure primitives they depend on
(regions, clusters, databases, CI systems, clouds). The simulation engine walks
this graph to compute blast radius and failover sequences.

The default topology models a realistic multi-cloud e-commerce platform; in
production it would be hydrated from a service catalog / CMDB / Terraform state.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple


@dataclass
class Node:
    id: str
    kind: str  # service | database | region | cluster | ci | cloud
    cloud: str = ""
    region: str = ""
    tier: int = 2  # 0 = edge/critical user-facing, higher = deeper dependency
    failover: str = ""  # node id of standby, if any
    metadata: dict = field(default_factory=dict)


# (from -> to) means "from depends on to".
@dataclass
class Edge:
    src: str
    dst: str
    relation: str  # runs_on | reads_from | deploys_via | replicates_to | hosted_in


# Relations that do NOT propagate a *runtime availability* outage. A service
# that only "deploys_via" Jenkins keeps running when Jenkins dies — it just
# can't ship. These edges are still traced for visualization, but excluded from
# the availability blast radius (unless the scenario opts them in).
NON_PROPAGATING_RELATIONS = {"deploys_via", "replicates_to"}


class Topology:
    def __init__(self) -> None:
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        # dst -> list of (src, relation) — who depends on dst, and how.
        self._dependents: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        self._dependencies: Dict[str, List[str]] = defaultdict(list)

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node

    def add_edge(self, src: str, dst: str, relation: str) -> None:
        self.edges.append(Edge(src, dst, relation))
        self._dependents[dst].append((src, relation))  # who depends on dst
        self._dependencies[src].append(dst)

    def dependents_of(self, node_id: str) -> List[Tuple[str, str]]:
        return self._dependents.get(node_id, [])

    def impacted_by(
        self, failed_nodes: Set[str], propagate_all: bool = False
    ) -> List[Tuple[str, int]]:
        """BFS upward through dependents. Returns (node_id, hop_distance).

        Edges whose relation is in NON_PROPAGATING_RELATIONS are skipped for the
        availability blast radius unless ``propagate_all`` is set (used by
        deployment/CI-centric scenarios that care about the deploy graph).
        """
        visited: Dict[str, int] = {n: 0 for n in failed_nodes}
        queue = deque((n, 0) for n in failed_nodes)
        while queue:
            current, dist = queue.popleft()
            for dep, relation in self.dependents_of(current):
                if not propagate_all and relation in NON_PROPAGATING_RELATIONS:
                    continue
                if dep not in visited:
                    visited[dep] = dist + 1
                    queue.append((dep, dist + 1))
        return [(n, d) for n, d in visited.items() if n not in failed_nodes]

    def trace_edges(self, failed_nodes: Set[str], impacted: Set[str]) -> List[dict]:
        relevant = failed_nodes | impacted
        return [
            {"from": e.src, "to": e.dst, "relation": e.relation}
            for e in self.edges
            if e.src in relevant and e.dst in relevant
        ]

    def services(self) -> List[Node]:
        return [n for n in self.nodes.values() if n.kind == "service"]


def _infra_skeleton() -> Topology:
    """Shared infrastructure primitives (clouds, regions, clusters, DB, CI).

    Every topology — the default demo and any import-derived one — is built on
    this same skeleton so the disaster scenarios (region/cluster/DB/CI failures)
    always have the nodes they target. Callers add services on top.
    """
    t = Topology()

    # ---- Clouds / regions / clusters ----
    t.add_node(Node("aws", "cloud", cloud="aws"))
    t.add_node(Node("azure", "cloud", cloud="azure"))
    t.add_node(Node("aws:us-east-1", "region", cloud="aws", region="us-east-1",
                    failover="aws:us-west-2"))
    t.add_node(Node("aws:us-west-2", "region", cloud="aws", region="us-west-2"))
    t.add_node(Node("azure:eastus", "region", cloud="azure", region="eastus"))
    t.add_node(Node("k8s:prod-east", "cluster", cloud="aws", region="us-east-1",
                    failover="k8s:prod-west"))
    t.add_node(Node("k8s:prod-west", "cluster", cloud="aws", region="us-west-2"))

    # ---- Data + CI ----
    t.add_node(Node("postgres-primary", "database", cloud="aws", region="us-east-1",
                    failover="postgres-replica", tier=3))
    t.add_node(Node("postgres-replica", "database", cloud="aws", region="us-west-2",
                    tier=3))
    t.add_node(Node("jenkins", "ci", cloud="aws", region="us-east-1", tier=4))

    # ---- Region/cluster/cloud hierarchy ----
    t.add_edge("aws:us-east-1", "aws", "hosted_in")
    t.add_edge("aws:us-west-2", "aws", "hosted_in")
    t.add_edge("azure:eastus", "azure", "hosted_in")
    t.add_edge("k8s:prod-east", "aws:us-east-1", "hosted_in")
    t.add_edge("k8s:prod-west", "aws:us-west-2", "hosted_in")
    t.add_edge("postgres-primary", "aws:us-east-1", "hosted_in")
    t.add_edge("postgres-replica", "aws:us-west-2", "hosted_in")
    t.add_edge("postgres-primary", "postgres-replica", "replicates_to")
    t.add_edge("jenkins", "aws:us-east-1", "hosted_in")
    return t


def default_topology() -> Topology:
    t = _infra_skeleton()

    # ---- Services (tiered) ----
    services = [
        ("api-gateway", 0, "k8s:prod-east"),
        ("checkout-service", 0, "k8s:prod-east"),
        ("payments-service", 0, "k8s:prod-east"),
        ("order-service", 1, "k8s:prod-east"),
        ("inventory-service", 1, "k8s:prod-east"),
        ("user-service", 1, "k8s:prod-east"),
        ("notification-service", 2, "azure:eastus"),
        ("analytics-service", 2, "azure:eastus"),
        ("search-service", 1, "k8s:prod-east"),
    ]
    for name, tier, host in services:
        node = t.nodes.get(host)
        t.add_node(
            Node(name, "service", cloud=node.cloud, region=node.region, tier=tier)
        )
        t.add_edge(name, host, "runs_on")

    # ---- Data + deploy dependencies ----
    db_consumers = [
        "order-service",
        "inventory-service",
        "user-service",
        "payments-service",
        "checkout-service",
        "search-service",
    ]
    for svc in db_consumers:
        t.add_edge(svc, "postgres-primary", "reads_from")
    for svc in [s[0] for s in services]:
        t.add_edge(svc, "jenkins", "deploys_via")

    # ---- Inter-service calls ----
    t.add_edge("checkout-service", "payments-service", "calls")
    t.add_edge("checkout-service", "inventory-service", "calls")
    t.add_edge("order-service", "checkout-service", "calls")
    t.add_edge("api-gateway", "order-service", "calls")
    t.add_edge("api-gateway", "user-service", "calls")
    t.add_edge("api-gateway", "search-service", "calls")
    return t


def topology_from_services(services: List[str], max_services: int = 12) -> Topology:
    """Build a topology whose services are an imported project's services,
    mapped onto the standard infrastructure skeleton.

    A git repo doesn't describe real infrastructure, so tiers/hosts are assigned
    heuristically: the first two services are treated as tier-0 (user-facing),
    the next three as tier-1, and the rest as tier-2 (hosted on Azure). This lets
    the existing region/cluster/DB/CI scenarios run against the imported app's
    own service names instead of the static demo set.
    """
    # De-dup, preserve order, cap for signal clarity.
    seen: Set[str] = set()
    svcs: List[str] = []
    for s in services:
        if s and s not in seen:
            seen.add(s)
            svcs.append(s)
        if len(svcs) >= max_services:
            break
    if not svcs:
        return default_topology()

    t = _infra_skeleton()
    tier0: List[str] = []
    for i, name in enumerate(svcs):
        tier = 0 if i < 2 else (1 if i < 5 else 2)
        host = "azure:eastus" if tier == 2 else "k8s:prod-east"
        node = t.nodes[host]
        t.add_node(
            Node(name, "service", cloud=node.cloud, region=node.region, tier=tier)
        )
        t.add_edge(name, host, "runs_on")
        if tier <= 1:
            t.add_edge(name, "postgres-primary", "reads_from")
        t.add_edge(name, "jenkins", "deploys_via")
        if tier == 0:
            tier0.append(name)

    # The tier-0 service acts as the gateway and calls everything deeper.
    gateway = tier0[0] if tier0 else svcs[0]
    for name in svcs:
        if name != gateway:
            t.add_edge(gateway, name, "calls")
    return t
