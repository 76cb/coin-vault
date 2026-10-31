"""Numista: the issue (year and mint) chosen for a coin, and a cache of catalogue answers.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("coin_details") as batch:
        batch.add_column(sa.Column("numista_issue_id", sa.Integer(), nullable=True))
    op.create_table(
        "provider_cache",
        sa.Column("provider_key", sa.String(30), primary_key=True),
        sa.Column("cache_key", sa.String(200), primary_key=True),
        sa.Column("data", sa.JSON()),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("provider_cache")
    with op.batch_alter_table("coin_details") as batch:
        batch.drop_column("numista_issue_id")
