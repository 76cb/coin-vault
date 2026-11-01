"""Goldbacks already saved: their gold set from the denomination, with its weight and .9999 fineness.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from app.services.goldbacks import FINENESS, gold_grams, gold_toz

    bind = op.get_bind()
    metal = sa.table(
        "item_metal_content", sa.column("item_id", sa.Integer), sa.column("metal", sa.String),
        sa.column("gross_weight_g", sa.Numeric(14, 6)), sa.column("fineness", sa.Numeric(6, 5)),
        sa.column("pure_toz", sa.Numeric(14, 6)), sa.column("source", sa.String), sa.column("composition_id", sa.Integer),
    )
    rows = bind.execute(sa.text(
        "SELECT g.item_id, g.denomination FROM goldback_details g JOIN items i ON i.id = g.item_id "
        "WHERE i.item_type = 'goldback' AND g.denomination IS NOT NULL"
    )).all()
    for item_id, denom in rows:
        bind.execute(metal.delete().where(metal.c.item_id == item_id))
        bind.execute(metal.insert().values(
            item_id=item_id, metal="Au", gross_weight_g=gold_grams(denom), fineness=FINENESS, pure_toz=gold_toz(denom),
            source="override", composition_id=None,
        ))


def downgrade() -> None:
    pass  # the figures stay; they're right either way
