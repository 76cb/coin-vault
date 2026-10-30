"""Initial schema (Milestone 1)

Revision ID: 0001
Revises: 
Create Date: 2026-10-30 19:22:16.254696
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('base_currency', sa.String(length=3), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('username', name=op.f('uq_users_username'))
    )
    op.create_table('api_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('prefix', sa.String(length=16), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('scopes', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_api_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_tokens')),
    sa.UniqueConstraint('prefix', name=op.f('uq_api_tokens_prefix'))
    )
    with op.batch_alter_table('api_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_api_tokens_user_id'), ['user_id'], unique=False)

    op.create_table('app_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('value', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_app_settings_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_app_settings')),
    sa.UniqueConstraint('owner_id', 'key', name='uq_app_settings_owner_key')
    )
    op.create_table('audit_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('actor_type', sa.String(length=10), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('entity', sa.String(length=40), nullable=False),
    sa.Column('entity_id', sa.Integer(), nullable=False),
    sa.Column('field', sa.String(length=60), nullable=False),
    sa.Column('old_value', sa.Text(), nullable=True),
    sa.Column('new_value', sa.Text(), nullable=True),
    sa.Column('request_id', sa.String(length=36), nullable=True),
    sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_audit_log_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_log'))
    )
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_log_entity_id'), ['entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_log_owner_id'), ['owner_id'], unique=False)

    op.create_table('compositions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=120), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('label', sa.String(length=200), nullable=False),
    sa.Column('country', sa.String(length=80), nullable=True),
    sa.Column('denomination', sa.String(length=80), nullable=True),
    sa.Column('year_from', sa.Integer(), nullable=True),
    sa.Column('year_to', sa.Integer(), nullable=True),
    sa.Column('mint_marks', sa.JSON(), nullable=True),
    sa.Column('metal', sa.String(length=2), nullable=False),
    sa.Column('fineness', sa.Numeric(precision=6, scale=5), nullable=True),
    sa.Column('gross_weight_g', sa.Numeric(precision=14, scale=6), nullable=True),
    sa.Column('pure_toz', sa.Numeric(precision=14, scale=6), nullable=False),
    sa.Column('per_face_unit', sa.Boolean(), nullable=False),
    sa.Column('citation', sa.Text(), nullable=True),
    sa.CheckConstraint("metal IN ('Au', 'Ag', 'Pt', 'Pd')", name=op.f('ck_compositions_metal')),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_compositions_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_compositions')),
    sa.UniqueConstraint('key', name=op.f('uq_compositions_key'))
    )
    op.create_table('documents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=12), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('doc_date', sa.Date(), nullable=True),
    sa.Column('storage_key', sa.String(length=255), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('mime', sa.String(length=40), nullable=False),
    sa.Column('bytes', sa.Integer(), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('receipt', 'invoice', 'certificate', 'assay_card', 'other')", name=op.f('ck_documents_kind')),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_documents_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_documents'))
    )
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documents_owner_id'), ['owner_id'], unique=False)

    op.create_table('locations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_locations_owner_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['parent_id'], ['locations.id'], name=op.f('fk_locations_parent_id_locations'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_locations'))
    )
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_locations_owner_id'), ['owner_id'], unique=False)

    op.create_table('sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('csrf_token', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_sessions_token_hash'))
    )
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sessions_user_id'), ['user_id'], unique=False)

    op.create_table('tags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_tags_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tags')),
    sa.UniqueConstraint('owner_id', 'name', name='uq_tags_owner_name')
    )
    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tags_owner_id'), ['owner_id'], unique=False)

    op.create_table('items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('item_type', sa.String(length=16), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('location_id', sa.Integer(), nullable=True),
    sa.Column('acquired_date', sa.Date(), nullable=True),
    sa.Column('purchase_price', sa.Numeric(precision=14, scale=4), nullable=True),
    sa.Column('purchase_fees', sa.Numeric(precision=14, scale=4), nullable=True),
    sa.Column('cost_basis_status', sa.String(length=16), nullable=False),
    sa.Column('purchase_source', sa.String(length=200), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('cover_photo_id', sa.Integer(), nullable=True),
    sa.Column('valuation_rule', sa.String(length=16), nullable=False),
    sa.Column('sale_date', sa.Date(), nullable=True),
    sa.Column('sale_price', sa.Numeric(precision=14, scale=4), nullable=True),
    sa.Column('sale_fees', sa.Numeric(precision=14, scale=4), nullable=True),
    sa.Column('sale_venue', sa.String(length=200), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("cost_basis_status IN ('known', 'estimated', 'unknown')", name=op.f('ck_items_cost_basis_status')),
    sa.CheckConstraint("item_type IN ('coin', 'bullion', 'bar', 'banknote', 'lot', 'other')", name=op.f('ck_items_item_type')),
    sa.CheckConstraint("status IN ('owned', 'for_sale', 'sold')", name=op.f('ck_items_status')),
    sa.CheckConstraint("valuation_rule IN ('max', 'melt', 'market', 'cost')", name=op.f('ck_items_valuation_rule')),
    sa.CheckConstraint('quantity >= 1', name=op.f('ck_items_quantity_positive')),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], name=op.f('fk_items_location_id_locations'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_items_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_items'))
    )
    with op.batch_alter_table('items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_items_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_items_item_type'), ['item_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_items_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_items_status'), ['status'], unique=False)

    op.create_table('banknote_details',
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('country', sa.String(length=80), nullable=True),
    sa.Column('denomination', sa.String(length=80), nullable=True),
    sa.Column('series', sa.String(length=80), nullable=True),
    sa.Column('serial_number', sa.String(length=60), nullable=True),
    sa.Column('pick_number', sa.String(length=30), nullable=True),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_banknote_details_item_id_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('item_id', name=op.f('pk_banknote_details'))
    )
    op.create_table('bar_details',
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('weight_value', sa.Numeric(precision=14, scale=6), nullable=True),
    sa.Column('weight_unit', sa.String(length=4), nullable=False),
    sa.Column('refiner', sa.String(length=120), nullable=True),
    sa.Column('serial_number', sa.String(length=60), nullable=True),
    sa.Column('has_assay_card', sa.Boolean(), nullable=False),
    sa.CheckConstraint("weight_unit IN ('g', 'ozt', 'kg', 'tola')", name=op.f('ck_bar_details_weight_unit')),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_bar_details_item_id_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('item_id', name=op.f('pk_bar_details'))
    )
    op.create_table('coin_details',
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('country', sa.String(length=80), nullable=True),
    sa.Column('denomination', sa.String(length=80), nullable=True),
    sa.Column('year', sa.Integer(), nullable=True),
    sa.Column('mint_mark', sa.String(length=10), nullable=True),
    sa.Column('series', sa.String(length=120), nullable=True),
    sa.Column('product_line', sa.String(length=120), nullable=True),
    sa.Column('mint', sa.String(length=120), nullable=True),
    sa.Column('diameter_mm', sa.Numeric(precision=7, scale=2), nullable=True),
    sa.Column('numista_id', sa.Integer(), nullable=True),
    sa.Column('pcgs_number', sa.String(length=20), nullable=True),
    sa.Column('redbook_number', sa.String(length=30), nullable=True),
    sa.Column('variety_notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_coin_details_item_id_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('item_id', name=op.f('pk_coin_details'))
    )
    op.create_table('document_links',
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_document_links_document_id_documents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_document_links_item_id_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('document_id', 'item_id', name=op.f('pk_document_links'))
    )
    op.create_table('item_condition',
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('grading', sa.String(length=8), nullable=False),
    sa.Column('sheldon_grade', sa.Integer(), nullable=True),
    sa.Column('grade_text', sa.String(length=60), nullable=True),
    sa.Column('grading_service', sa.String(length=30), nullable=True),
    sa.Column('cert_number', sa.String(length=40), nullable=True),
    sa.Column('designations', sa.JSON(), nullable=False),
    sa.Column('details_reason', sa.String(length=120), nullable=True),
    sa.CheckConstraint("grading IN ('raw', 'slabbed')", name=op.f('ck_item_condition_grading')),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_item_condition_item_id_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('item_id', name=op.f('pk_item_condition'))
    )
    op.create_table('item_metal_content',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('metal', sa.String(length=2), nullable=False),
    sa.Column('gross_weight_g', sa.Numeric(precision=14, scale=6), nullable=True),
    sa.Column('fineness', sa.Numeric(precision=6, scale=5), nullable=True),
    sa.Column('pure_toz', sa.Numeric(precision=14, scale=6), nullable=True),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.Column('composition_id', sa.Integer(), nullable=True),
    sa.CheckConstraint("metal IN ('Au', 'Ag', 'Pt', 'Pd')", name=op.f('ck_item_metal_content_metal')),
    sa.CheckConstraint("source IN ('reference', 'computed', 'override')", name=op.f('ck_item_metal_content_source')),
    sa.ForeignKeyConstraint(['composition_id'], ['compositions.id'], name=op.f('fk_item_metal_content_composition_id_compositions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_item_metal_content_item_id_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_item_metal_content'))
    )
    with op.batch_alter_table('item_metal_content', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_item_metal_content_item_id'), ['item_id'], unique=False)

    op.create_table('item_tags',
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_item_tags_item_id_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], name=op.f('fk_item_tags_tag_id_tags'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('item_id', 'tag_id', name=op.f('pk_item_tags'))
    )
    op.create_table('lot_details',
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('face_value', sa.Numeric(precision=14, scale=4), nullable=True),
    sa.Column('face_currency', sa.String(length=3), nullable=False),
    sa.Column('composition_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['composition_id'], ['compositions.id'], name=op.f('fk_lot_details_composition_id_compositions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_lot_details_item_id_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('item_id', name=op.f('pk_lot_details'))
    )
    op.create_table('other_details',
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('attributes', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_other_details_item_id_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('item_id', name=op.f('pk_other_details'))
    )
    op.create_table('photos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=12), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('storage_key', sa.String(length=255), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('phash', sa.String(length=16), nullable=True),
    sa.Column('mime', sa.String(length=40), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('bytes', sa.Integer(), nullable=False),
    sa.Column('quality', sa.JSON(), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("role IN ('obverse', 'reverse', 'edge', 'slab_front', 'slab_back', 'other')", name=op.f('ck_photos_role')),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], name=op.f('fk_photos_item_id_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_photos'))
    )
    with op.batch_alter_table('photos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_photos_item_id'), ['item_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_photos_sha256'), ['sha256'], unique=False)

    # items.cover_photo_id -> photos.id is circular, so it is added once photos exists.
    # SQLite cannot add constraints after creation; the app keeps the reference valid there.
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_items_cover_photo_id_photos", "items", "photos", ["cover_photo_id"], ["id"], ondelete="SET NULL"
        )

    op.create_table('upload_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('batch_id', sa.String(length=36), nullable=False),
    sa.Column('pairing_rule', sa.String(length=10), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=True),
    sa.Column('status', sa.String(length=14), nullable=False),
    sa.Column('resulting_item_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("pairing_rule IN ('pattern', 'order', 'single', 'manual')", name=op.f('ck_upload_groups_pairing_rule')),
    sa.CheckConstraint("status IN ('pending', 'attached', 'created_item', 'discarded')", name=op.f('ck_upload_groups_status')),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_upload_groups_owner_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['resulting_item_id'], ['items.id'], name=op.f('fk_upload_groups_resulting_item_id_items'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_upload_groups'))
    )
    with op.batch_alter_table('upload_groups', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_upload_groups_batch_id'), ['batch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_upload_groups_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_upload_groups_status'), ['status'], unique=False)

    op.create_table('upload_files',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('group_id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('storage_key', sa.String(length=255), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('phash', sa.String(length=16), nullable=True),
    sa.Column('mime', sa.String(length=40), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('bytes', sa.Integer(), nullable=False),
    sa.Column('quality', sa.JSON(), nullable=False),
    sa.Column('suggested_role', sa.String(length=12), nullable=False),
    sa.Column('duplicate_of_photo_id', sa.Integer(), nullable=True),
    sa.Column('duplicate_kind', sa.String(length=8), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("suggested_role IN ('obverse', 'reverse', 'edge', 'slab_front', 'slab_back', 'other')", name=op.f('ck_upload_files_suggested_role')),
    sa.ForeignKeyConstraint(['duplicate_of_photo_id'], ['photos.id'], name=op.f('fk_upload_files_duplicate_of_photo_id_photos'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['group_id'], ['upload_groups.id'], name=op.f('fk_upload_files_group_id_upload_groups'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_upload_files_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_upload_files'))
    )
    with op.batch_alter_table('upload_files', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_upload_files_group_id'), ['group_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_upload_files_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_upload_files_sha256'), ['sha256'], unique=False)



def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_items_cover_photo_id_photos", "items", type_="foreignkey")
    with op.batch_alter_table('upload_files', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_upload_files_sha256'))
        batch_op.drop_index(batch_op.f('ix_upload_files_owner_id'))
        batch_op.drop_index(batch_op.f('ix_upload_files_group_id'))

    op.drop_table('upload_files')
    with op.batch_alter_table('upload_groups', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_upload_groups_status'))
        batch_op.drop_index(batch_op.f('ix_upload_groups_owner_id'))
        batch_op.drop_index(batch_op.f('ix_upload_groups_batch_id'))

    op.drop_table('upload_groups')
    with op.batch_alter_table('photos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_photos_sha256'))
        batch_op.drop_index(batch_op.f('ix_photos_item_id'))

    op.drop_table('photos')
    op.drop_table('other_details')
    op.drop_table('lot_details')
    op.drop_table('item_tags')
    with op.batch_alter_table('item_metal_content', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_item_metal_content_item_id'))

    op.drop_table('item_metal_content')
    op.drop_table('item_condition')
    op.drop_table('document_links')
    op.drop_table('coin_details')
    op.drop_table('bar_details')
    op.drop_table('banknote_details')
    with op.batch_alter_table('items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_items_status'))
        batch_op.drop_index(batch_op.f('ix_items_owner_id'))
        batch_op.drop_index(batch_op.f('ix_items_item_type'))
        batch_op.drop_index(batch_op.f('ix_items_deleted_at'))

    op.drop_table('items')
    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tags_owner_id'))

    op.drop_table('tags')
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sessions_user_id'))

    op.drop_table('sessions')
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_locations_owner_id'))

    op.drop_table('locations')
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documents_owner_id'))

    op.drop_table('documents')
    op.drop_table('compositions')
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_log_owner_id'))
        batch_op.drop_index(batch_op.f('ix_audit_log_entity_id'))

    op.drop_table('audit_log')
    op.drop_table('app_settings')
    with op.batch_alter_table('api_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_api_tokens_user_id'))

    op.drop_table('api_tokens')
    op.drop_table('users')
