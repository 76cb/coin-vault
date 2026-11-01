"""Goldbacks: their own item type, with the series (state), denomination and year.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "item_type IN ('coin', 'bullion', 'bar', 'banknote', 'lot', 'other')"
NEW = "item_type IN ('coin', 'bullion', 'bar', 'banknote', 'goldback', 'lot', 'other')"


def _item_type_check(condition: str) -> None:
    if op.get_bind().dialect.name == "sqlite":
        # SQLite can't change a CHECK in place: the table is rebuilt, with every other constraint kept as reflected
        with op.batch_alter_table("items", recreate="always", reflect_kwargs={"resolve_fks": False}) as batch:
            batch.drop_constraint(op.f("ck_items_item_type"), type_="check")
            batch.create_check_constraint("item_type", condition)
    else:
        op.drop_constraint(op.f("ck_items_item_type"), "items", type_="check")
        op.create_check_constraint("item_type", "items", condition)


def upgrade() -> None:
    op.create_table(
        "goldback_details",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=60), nullable=True),
        sa.Column("denomination", sa.Numeric(8, 3), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("serial_number", sa.String(length=60), nullable=True),
        sa.Column("variety", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], name=op.f("fk_goldback_details_item_id_items"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_goldback_details")),
    )
    _item_type_check(NEW)


def downgrade() -> None:
    op.execute("DELETE FROM items WHERE item_type = 'goldback'")
    _item_type_check(OLD)
    op.drop_table("goldback_details")
