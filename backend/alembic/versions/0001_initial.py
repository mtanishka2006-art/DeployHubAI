"""initial schema

Baseline migration. Creates the full schema from the SQLAlchemy metadata so the
models remain the single source of truth for the initial revision. Subsequent
schema changes should be produced with `alembic revision --autogenerate`.

Revision ID: 0001_initial
Revises:
Create Date: 2026-01-01 00:00:00
"""
from typing import Sequence, Union

from alembic import op

from app.db.base import Base
from app.db import models  # noqa: F401  (register all tables on the metadata)

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
