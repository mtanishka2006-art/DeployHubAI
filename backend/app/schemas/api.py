"""Pydantic request/response schemas for the public API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class UserInfo(BaseModel):
    username: str
    role: str


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
class MetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source: str
    service: str
    environment: str
    metric_name: str
    value: float
    unit: str
    timestamp: datetime


# --------------------------------------------------------------------------- #
# Incidents
# --------------------------------------------------------------------------- #
class IncidentCreate(BaseModel):
    title: str
    description: str = ""
    service: str
    environment: str = "prod"
    severity: str = "medium"
    source: str = "manual"


class RecoveryActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action: str
    rationale: str
    risk: str
    priority: int
    status: str


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str
    severity: str
    status: str
    service: str
    environment: str
    source: str
    root_cause: Optional[str] = None
    detected_at: datetime
    resolved_at: Optional[datetime] = None


class IncidentDetail(IncidentOut):
    recommended_actions: List[RecoveryActionOut] = Field(default_factory=list)
    similar_incidents: List[Dict[str, Any]] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Deployments
# --------------------------------------------------------------------------- #
class DeploymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source: str
    service: str
    environment: str
    version: str
    commit: str
    actor: str
    status: str
    duration_seconds: int
    timestamp: datetime


# --------------------------------------------------------------------------- #
# Disaster Recovery
# --------------------------------------------------------------------------- #
class BackupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    system: str
    service: str
    status: str
    last_backup: datetime
    rpo_minutes: int


class ReplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    source: str
    target: str
    status: str
    lag_seconds: int


class FailoverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    service: str
    region: str
    status: str
    last_tested: Optional[datetime] = None


class DRStatusResponse(BaseModel):
    dr_score: Optional[int] = None  # None => not measurable (no DR data source)
    readiness: str
    backups: List[BackupOut]
    replication: List[ReplicationOut]
    failovers: List[FailoverOut]


class DREventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_type: str
    service: str
    region: str
    status: str
    timestamp: datetime
    detail: str


# --------------------------------------------------------------------------- #
# Memory / RAG
# --------------------------------------------------------------------------- #
class MemorySearchRequest(BaseModel):
    query: str
    collection: str = "incident_memory"
    k: int = 5


class MemoryResult(BaseModel):
    id: str
    title: str
    summary: str
    root_cause: str = ""
    recovery_actions: List[str] = Field(default_factory=list)
    outcome: str = ""
    score: float = 0.0
    occurred_at: Optional[str] = None


class MemorySearchResponse(BaseModel):
    results: List[MemoryResult]


# --------------------------------------------------------------------------- #
# Mission Control
# --------------------------------------------------------------------------- #
class MissionControlRequest(BaseModel):
    incident_id: Optional[int] = None
    description: Optional[str] = None
    service: Optional[str] = None
    environment: str = "prod"
    severity: str = "high"


class RecommendedAction(BaseModel):
    action: str
    rationale: str = ""
    risk: str = "low"
    priority: int = 1


class AgentBlock(BaseModel):
    health_status: Optional[str] = None
    root_cause: Optional[str] = None
    dr_score: Optional[int] = None
    readiness: Optional[str] = None
    recommendations: Optional[List[Any]] = None
    confidence: float = 0.0


class MissionControlReportOut(BaseModel):
    incident_id: Optional[int]
    severity: str = "medium"
    system_health: str
    root_cause: str
    dr_readiness: str
    similar_incidents: List[Dict[str, Any]] = Field(default_factory=list)
    recommended_actions: List[RecommendedAction] = Field(default_factory=list)
    executive_summary: str
    monitoring: Dict[str, Any] = Field(default_factory=dict)
    rca: Dict[str, Any] = Field(default_factory=dict)
    dr: Dict[str, Any] = Field(default_factory=dict)
    recovery: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #
class SimulationRequest(BaseModel):
    scenario_type: str
    target: Optional[str] = None
    region: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class AffectedService(BaseModel):
    service: str
    impact: str
    environment: str = "prod"


class BlastRadius(BaseModel):
    service_count: int
    severity: str
    description: str


class FailoverStep(BaseModel):
    step: int
    action: str
    eta_minutes: int


class DependencyEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str
    relation: str

    model_config = ConfigDict(populate_by_name=True)


class SimulationResponse(BaseModel):
    scenario_type: str
    summary: str
    affected_services: List[AffectedService]
    blast_radius: BlastRadius
    estimated_downtime_minutes: int
    recovery_strategy: List[str]
    failover_sequence: List[FailoverStep]
    dependency_trace: List[Dict[str, Any]]


# --------------------------------------------------------------------------- #
# Overview dashboard aggregate
# --------------------------------------------------------------------------- #
class HealthByService(BaseModel):
    service: str
    score: int
    status: str
    connectors: List[str] = Field(default_factory=list)  # live data sources


class SystemHealth(BaseModel):
    status: str
    score: int


class DRReadiness(BaseModel):
    score: Optional[int] = None  # None => not measurable from the connected source
    readiness: str


class OverviewResponse(BaseModel):
    system_health: SystemHealth
    active_incidents: int
    recovery_success_rate: float
    dr_readiness: DRReadiness
    recent_deployments: List[DeploymentOut]
    incident_timeline: List[Dict[str, Any]]
    health_by_service: List[HealthByService]


# --------------------------------------------------------------------------- #
# App Connector Hub
# --------------------------------------------------------------------------- #
class ConnectorField(BaseModel):
    name: str
    label: str
    type: str = "text"
    placeholder: str = ""
    required: bool = True


class AvailableConnector(BaseModel):
    app_type: str
    label: str
    description: str
    icon: str
    live_supported: bool
    upload: bool = False  # true => upload a .zip instead of credentials
    fields: List[ConnectorField]


class ConnectConnectorRequest(BaseModel):
    app_type: str
    name: Optional[str] = None
    credentials: Dict[str, Any] = Field(default_factory=dict)
    polling_interval_seconds: Optional[int] = None
    replace: bool = True  # used by git_repo: wipe other data so only this shows


class ConnectedAppOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    app_type: str
    status: str
    last_synced_at: Optional[datetime] = None
    last_error: str = ""
    polling_interval_seconds: int
    events_ingested: int
    created_by: str = ""
    created_at: Optional[datetime] = None


class ConnectorEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    app_type: str
    source: str
    event_type: str
    service: str
    severity: str
    summary: str
    timestamp: datetime


class LogEntryOut(BaseModel):
    """A single ingested log line, surfaced on the dedicated Logs page."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    source: str
    app_type: str
    service: str
    severity: str
    message: str = Field(validation_alias="summary")
    timestamp: datetime


class SyncResult(BaseModel):
    ok: bool
    message: str
    events_ingested: int = 0
    app: Optional[ConnectedAppOut] = None


class ImportResult(BaseModel):
    ok: bool
    message: str
    app_name: str
    services: List[str]
    commits: int
    deployments: int
    incidents: int
    pipelines: int = 0
    events_ingested: int
    app: Optional[ConnectedAppOut] = None


class PipelineOut(BaseModel):
    id: int
    provider: str
    name: str
    file_path: str
    triggers: List[str] = Field(default_factory=list)
    stages: List[str] = Field(default_factory=list)
    status: str
    app_name: str
