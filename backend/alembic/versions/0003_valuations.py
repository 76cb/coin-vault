"""Market values per item: typed in, or the median of sold listings.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-30 22:31:42.078651
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('valuations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('value_each', sa.Numeric(precision=14, scale=4), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('as_of', sa.Date(), nullable=False),
    sa.Column('source', sa.String(length=200), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('details', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('manual', 'comps')", name=op.f('ck_valuations_kind')),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_valuations_item_id_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_valuations'))
    )
    with op.batch_alter_table('valuations', schema=None) as batch_op:
        batch_op.create_index('ix_valuations_item_asof', ['item_id', 'as_of'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('valuations', schema=None) as batch_op:
        batch_op.drop_index('ix_valuations_item_asof')

    op.drop_table('valuations')
