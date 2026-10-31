"""Spot prices, provider settings, quotas, call log, system settings; seed compositions (Milestone 2)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30 21:29:18.990292
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('api_call_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('provider_key', sa.String(length=30), nullable=False),
    sa.Column('endpoint', sa.String(length=120), nullable=False),
    sa.Column('context', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('http_status', sa.Integer(), nullable=True),
    sa.Column('cost', sa.Integer(), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_call_log'))
    )
    with op.batch_alter_table('api_call_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_api_call_log_at'), ['at'], unique=False)
        batch_op.create_index(batch_op.f('ix_api_call_log_provider_key'), ['provider_key'], unique=False)

    op.create_table('api_quota_periods',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('provider_key', sa.String(length=30), nullable=False),
    sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used', sa.Integer(), nullable=False),
    sa.Column('provider_limit', sa.Integer(), nullable=True),
    sa.Column('provider_used', sa.Integer(), nullable=True),
    sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_quota_periods')),
    sa.UniqueConstraint('provider_key', 'period_start', name='uq_api_quota_periods_provider_start')
    )
    with op.batch_alter_table('api_quota_periods', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_api_quota_periods_provider_key'), ['provider_key'], unique=False)

    op.create_table('provider_configs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('provider_key', sa.String(length=30), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('api_key_encrypted', sa.Text(), nullable=True),
    sa.Column('api_key_last4', sa.String(length=4), nullable=True),
    sa.Column('quota_cap', sa.Integer(), nullable=True),
    sa.Column('settings', sa.JSON(), nullable=False),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('consecutive_failures', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('spot', 'comps', 'catalog', 'cert')", name=op.f('ck_provider_configs_kind')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_provider_configs')),
    sa.UniqueConstraint('provider_key', name=op.f('uq_provider_configs_provider_key'))
    )
    op.create_table('spot_prices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('metal', sa.String(length=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('price_per_toz', sa.Numeric(precision=14, scale=4), nullable=False),
    sa.Column('source', sa.String(length=30), nullable=False),
    sa.Column('source_timestamp', sa.DateTime(timezone=True), nullable=True),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("metal IN ('Au', 'Ag', 'Pt', 'Pd')", name=op.f('ck_spot_prices_metal')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_spot_prices'))
    )
    with op.batch_alter_table('spot_prices', schema=None) as batch_op:
        batch_op.create_index('ix_spot_prices_lookup', ['metal', 'currency', 'fetched_at'], unique=False)

    op.create_table('system_settings',
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('value', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_system_settings'))
    )
    from app.compositions_seed import ROWS

    compositions = sa.table(
        "compositions",
        sa.column("key", sa.String), sa.column("owner_id", sa.Integer), sa.column("label", sa.String),
        sa.column("country", sa.String), sa.column("denomination", sa.String), sa.column("year_from", sa.Integer),
        sa.column("year_to", sa.Integer), sa.column("mint_marks", sa.JSON), sa.column("metal", sa.String),
        sa.column("fineness", sa.Numeric), sa.column("gross_weight_g", sa.Numeric), sa.column("pure_toz", sa.Numeric),
        sa.column("per_face_unit", sa.Boolean), sa.column("citation", sa.Text),
    )
    existing = {r[0] for r in op.get_bind().execute(sa.text("SELECT key FROM compositions"))}
    op.bulk_insert(compositions, [dict(r, owner_id=None) for r in ROWS if r["key"] not in existing])


def downgrade() -> None:
    from app.compositions_seed import ROWS

    keys = ", ".join(f"'{r['key']}'" for r in ROWS)
    op.execute(f"DELETE FROM compositions WHERE owner_id IS NULL AND key IN ({keys})")
    op.drop_table('system_settings')
    with op.batch_alter_table('spot_prices', schema=None) as batch_op:
        batch_op.drop_index('ix_spot_prices_lookup')

    op.drop_table('spot_prices')
    op.drop_table('provider_configs')
    with op.batch_alter_table('api_quota_periods', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_api_quota_periods_provider_key'))

    op.drop_table('api_quota_periods')
    with op.batch_alter_table('api_call_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_api_call_log_provider_key'))
        batch_op.drop_index(batch_op.f('ix_api_call_log_at'))

    op.drop_table('api_call_log')
