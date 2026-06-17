"""App Connector Hub: connected_apps + connector_events

Revision ID: 0002_connector_hub
Revises: 0001_initial
Create Date: 2026-01-02 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_connector_hub"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "connected_apps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("app_type", sa.String(length=60), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("polling_interval_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("events_ingested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_connected_apps_app_type", "connected_apps", ["app_type"])

    op.create_table(
        "connector_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connected_app_id", sa.Integer(), nullable=False),
        sa.Column("app_type", sa.String(length=60), nullable=False),
        sa.Column("source", sa.String(length=60), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("service", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="info"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("timestamp", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["connected_app_id"], ["connected_apps.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_connector_events_connected_app_id", "connector_events", ["connected_app_id"]
    )
    op.create_index("ix_connector_events_app_type", "connector_events", ["app_type"])
    op.create_index("ix_connector_events_service", "connector_events", ["service"])
    op.create_index("ix_connector_events_timestamp", "connector_events", ["timestamp"])


def downgrade() -> None:
    op.drop_table("connector_events")
    op.drop_table("connected_apps")
