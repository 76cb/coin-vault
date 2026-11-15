"""Inventory checks (items.verified_at), read-only logins (users.viewer_of), spot price alerts and the want list.

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("items", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("viewer_of", sa.Integer(), nullable=True))
        batch.create_foreign_key(op.f("fk_users_viewer_of_users"), "users", ["viewer_of"], ["id"], ondelete="CASCADE")
    op.create_table(
        "spot_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("metal", sa.String(length=2), nullable=False),
        sa.Column("direction", sa.String(length=5), nullable=False),
        sa.Column("price", sa.Numeric(14, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggered_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("metal IN ('Au', 'Ag', 'Pt', 'Pd')", name=op.f("ck_spot_alerts_metal")),
        sa.CheckConstraint("direction IN ('above', 'below')", name=op.f("ck_spot_alerts_direction")),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_spot_alerts_owner_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_spot_alerts")),
    )
    op.create_index(op.f("ix_spot_alerts_owner_id"), "spot_alerts", ["owner_id"], unique=False)
    op.create_table(
        "want_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("target_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("found_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("found_item_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["found_item_id"], ["items.id"], name=op.f("fk_want_items_found_item_id_items"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_want_items_owner_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_want_items")),
    )
    op.create_index(op.f("ix_want_items_owner_id"), "want_items", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_table("want_items")
    op.drop_table("spot_alerts")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint(op.f("fk_users_viewer_of_users"), type_="foreignkey")
        batch.drop_column("viewer_of")
    op.drop_column("items", "verified_at")
