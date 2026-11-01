"""A coin's composition in words and its weight, filled in for US coins with no precious metal.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("coin_details") as batch:
        batch.add_column(sa.Column("composition", sa.String(160), nullable=True))
        batch.add_column(sa.Column("weight_g", sa.Numeric(12, 4), nullable=True))

    # coins already in the collection: fill in the ones with no metal content recorded
    from app.services.base_metals import lookup

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT c.item_id, c.country, c.denomination, c.year, c.mint_mark, c.series FROM coin_details c "
        "JOIN items i ON i.id = c.item_id WHERE i.item_type = 'coin' AND c.year IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM item_metal_content m WHERE m.item_id = c.item_id)"
    )).all()
    coins = sa.table("coin_details", sa.column("item_id", sa.Integer), sa.column("composition", sa.String),
                     sa.column("weight_g", sa.Numeric(12, 4)))  # typed, so the weight binds as a number everywhere
    for item_id, country, denomination, year, mint_mark, series in rows:
        hit = lookup(country, denomination, year, mint_mark, series)
        if hit is not None:
            bind.execute(coins.update().where(coins.c.item_id == item_id).values(composition=hit.composition, weight_g=hit.weight_g))


def downgrade() -> None:
    with op.batch_alter_table("coin_details") as batch:
        batch.drop_column("weight_g")
        batch.drop_column("composition")
