"""Pipelines: CI/CD pipeline definitions detected from connected sources

Revision ID: 0003_pipelines
Revises: 0002_connector_hub
Create Date: 2026-01-03 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_pipelines"
down_revision: Union[str, None] = "0002_connector_hub"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipelines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connected_app_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("file_path", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("triggers", sa.JSON(), nullable=True),
        sa.Column("stages", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="defined"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["connected_app_id"], ["connected_apps.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_pipelines_connected_app_id", "pipelines", ["connected_app_id"])
    op.create_index("ix_pipelines_provider", "pipelines", ["provider"])


def downgrade() -> None:
    op.drop_table("pipelines")
