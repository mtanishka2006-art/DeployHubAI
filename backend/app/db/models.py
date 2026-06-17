"""SQLAlchemy ORM models — the Data Storage Layer.

Every table maps to a domain entity in the platform:

  User                    -> auth / RBAC
  InfrastructureMetric    -> time-series health metrics
  Incident                -> detected/active incidents
  Deployment              -> CI/CD deployment records
  DisasterRecoveryEvent   -> DR system events
  Backup                  -> backup system snapshots
  FailoverEvent           -> failover monitoring events
  ReplicationStatus       -> replication health
  RecoveryAction          -> recommended/executed recovery actions
  HistoricalIncident      -> resolved incidents used for learning (RAG source)
  AgentOutput             -> raw output of each AI agent run
  MissionControlReport    -> unified incident report (orchestrator output)
  SimulationReport        -> disaster simulation results
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utcnow


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Severity(str, enum.Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"


class DeploymentStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    IN_PROGRESS = "in_progress"


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(40), default="Viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
class InfrastructureMetric(Base, TimestampMixin):
    __tablename__ = "infrastructure_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(60), index=True)
    service: Mapped[str] = mapped_column(String(120), index=True)
    environment: Mapped[str] = mapped_column(String(40), index=True, default="prod")
    metric_name: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(40), default="")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


# --------------------------------------------------------------------------- #
# Incidents
# --------------------------------------------------------------------------- #
class Incident(Base, TimestampMixin):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(20), default=Severity.MEDIUM.value)
    status: Mapped[str] = mapped_column(String(20), default=IncidentStatus.OPEN.value)
    service: Mapped[str] = mapped_column(String(120), index=True)
    environment: Mapped[str] = mapped_column(String(40), default="prod")
    source: Mapped[str] = mapped_column(String(60), default="")
    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    recovery_actions: Mapped[list["RecoveryAction"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )


# --------------------------------------------------------------------------- #
# Deployments
# --------------------------------------------------------------------------- #
class Deployment(Base, TimestampMixin):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(60), default="")  # jenkins / gha
    service: Mapped[str] = mapped_column(String(120), index=True)
    environment: Mapped[str] = mapped_column(String(40), default="prod")
    version: Mapped[str] = mapped_column(String(80), default="")
    commit: Mapped[str] = mapped_column(String(80), default="")
    actor: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(
        String(20), default=DeploymentStatus.SUCCESS.value
    )
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


# --------------------------------------------------------------------------- #
# Disaster Recovery
# --------------------------------------------------------------------------- #
class DisasterRecoveryEvent(Base, TimestampMixin):
    __tablename__ = "disaster_recovery_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    service: Mapped[str] = mapped_column(String(120), index=True)
    region: Mapped[str] = mapped_column(String(60), default="")
    status: Mapped[str] = mapped_column(String(40), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class Backup(Base, TimestampMixin):
    __tablename__ = "backups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    system: Mapped[str] = mapped_column(String(120), index=True)
    service: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(40), default="healthy")
    last_backup: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    rpo_minutes: Mapped[int] = mapped_column(Integer, default=60)
    size_gb: Mapped[float] = mapped_column(Float, default=0.0)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class FailoverEvent(Base, TimestampMixin):
    __tablename__ = "failover_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service: Mapped[str] = mapped_column(String(120), index=True)
    region: Mapped[str] = mapped_column(String(60), default="")
    target_region: Mapped[str] = mapped_column(String(60), default="")
    status: Mapped[str] = mapped_column(String(40), default="ready")
    last_tested: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rto_minutes: Mapped[int] = mapped_column(Integer, default=30)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class ReplicationStatus(Base, TimestampMixin):
    __tablename__ = "replication_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(120))
    target: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="in_sync")
    lag_seconds: Mapped[int] = mapped_column(Integer, default=0)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


# --------------------------------------------------------------------------- #
# Recovery
# --------------------------------------------------------------------------- #
class RecoveryAction(Base, TimestampMixin):
    __tablename__ = "recovery_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    risk: Mapped[str] = mapped_column(String(20), default="low")
    priority: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(40), default="recommended")
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    incident: Mapped[Optional["Incident"]] = relationship(
        back_populates="recovery_actions"
    )


# --------------------------------------------------------------------------- #
# Learning corpus (RAG source of truth, mirrored into the vector store)
# --------------------------------------------------------------------------- #
class HistoricalIncident(Base, TimestampMixin):
    __tablename__ = "historical_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    summary: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str] = mapped_column(Text, default="")
    recovery_actions: Mapped[list] = mapped_column(JSON, default=list)
    outcome: Mapped[str] = mapped_column(Text, default="")
    service: Mapped[str] = mapped_column(String(120), default="")
    severity: Mapped[str] = mapped_column(String(20), default=Severity.MEDIUM.value)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    embedded: Mapped[bool] = mapped_column(Boolean, default=False)


# --------------------------------------------------------------------------- #
# Agent + orchestrator outputs
# --------------------------------------------------------------------------- #
class AgentOutput(Base, TimestampMixin):
    __tablename__ = "agent_outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_name: Mapped[str] = mapped_column(String(80), index=True)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class MissionControlReport(Base, TimestampMixin):
    __tablename__ = "mission_control_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    system_health: Mapped[str] = mapped_column(String(40), default="")
    root_cause: Mapped[str] = mapped_column(Text, default="")
    dr_readiness: Mapped[str] = mapped_column(String(40), default="")
    similar_incidents: Mapped[list] = mapped_column(JSON, default=list)
    recommended_actions: Mapped[list] = mapped_column(JSON, default=list)
    executive_summary: Mapped[str] = mapped_column(Text, default="")
    raw_outputs: Mapped[dict] = mapped_column(JSON, default=dict)


class ConnectedApp(Base, TimestampMixin):
    """A third-party application connected via the App Connector Hub.

    Credentials are stored encrypted (Fernet) in ``credentials_encrypted`` and
    are never returned to the client.
    """

    __tablename__ = "connected_apps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    app_type: Mapped[str] = mapped_column(String(60), index=True)
    credentials_encrypted: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending | connected | error | disconnected
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str] = mapped_column(Text, default="")
    polling_interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    events_ingested: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(120), default="")

    events: Mapped[list["ConnectorEvent"]] = relationship(
        back_populates="app", cascade="all, delete-orphan"
    )


class ConnectorEvent(Base, TimestampMixin):
    """A lightweight log of each event a connector ingested (for the live feed
    and dashboard 'which connector feeds this service' badges)."""

    __tablename__ = "connector_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connected_app_id: Mapped[int] = mapped_column(
        ForeignKey("connected_apps.id", ondelete="CASCADE"), index=True
    )
    app_type: Mapped[str] = mapped_column(String(60), index=True)
    source: Mapped[str] = mapped_column(String(60))
    event_type: Mapped[str] = mapped_column(String(40))
    service: Mapped[str] = mapped_column(String(120), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info")
    summary: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    app: Mapped["ConnectedApp"] = relationship(back_populates="events")


class Pipeline(Base, TimestampMixin):
    """A CI/CD pipeline definition detected in a connected source's repo."""

    __tablename__ = "pipelines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connected_app_id: Mapped[int] = mapped_column(
        ForeignKey("connected_apps.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40), index=True)  # github_actions…
    name: Mapped[str] = mapped_column(String(200))
    file_path: Mapped[str] = mapped_column(String(255), default="")
    triggers: Mapped[list] = mapped_column(JSON, default=list)
    stages: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="defined")


class SimulationReport(Base, TimestampMixin):
    __tablename__ = "simulation_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_type: Mapped[str] = mapped_column(String(80), index=True)
    target: Mapped[str] = mapped_column(String(120), default="")
    region: Mapped[str] = mapped_column(String(60), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    affected_services: Mapped[list] = mapped_column(JSON, default=list)
    blast_radius: Mapped[dict] = mapped_column(JSON, default=dict)
    estimated_downtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    recovery_strategy: Mapped[list] = mapped_column(JSON, default=list)
    failover_sequence: Mapped[list] = mapped_column(JSON, default=list)
    dependency_trace: Mapped[list] = mapped_column(JSON, default=list)
