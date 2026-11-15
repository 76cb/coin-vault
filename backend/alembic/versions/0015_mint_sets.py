"""Mint and proof sets: their own item type, with the coins inside each set listed.

Silver proof sets saved before this (as a coin with the denomination "set" and one whole-set silver figure)
become sets with their coins broken out, when that figure was still the untouched reference one.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "item_type IN ('coin', 'bullion', 'bar', 'banknote', 'goldback', 'lot', 'other')"
NEW = "item_type IN ('coin', 'bullion', 'set', 'bar', 'banknote', 'goldback', 'lot', 'other')"


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
        "set_details",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=80), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("mint_mark", sa.String(length=10), nullable=True),
        sa.Column("set_kind", sa.String(length=16), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=True),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], name=op.f("fk_set_details_item_id_items"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_set_details")),
    )
    op.create_table(
        "set_coins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("denomination", sa.String(length=80), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("mint_mark", sa.String(length=10), nullable=True),
        sa.Column("series", sa.String(length=120), nullable=True),
        sa.Column("composition", sa.String(length=160), nullable=True),
        sa.Column("weight_g", sa.Numeric(12, 4), nullable=True),
        sa.Column("metal", sa.String(length=2), nullable=True),
        sa.Column("fineness", sa.Numeric(6, 5), nullable=True),
        sa.Column("pure_toz", sa.Numeric(14, 6), nullable=True),
        sa.Column("composition_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("quantity >= 1", name=op.f("ck_set_coins_quantity_positive")),
        sa.ForeignKeyConstraint(["composition_id"], ["compositions.id"], name=op.f("fk_set_coins_composition_id_compositions"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], name=op.f("fk_set_coins_item_id_items"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_set_coins")),
    )
    op.create_index(op.f("ix_set_coins_item_id"), "set_coins", ["item_id"], unique=False)
    _item_type_check(NEW)
    _break_out_saved_sets()


def _break_out_saved_sets() -> None:
    from app.services import mint_sets

    bind = op.get_bind()
    num = {"weight_g": sa.Numeric(12, 4), "gross_weight_g": sa.Numeric(14, 6), "fineness": sa.Numeric(6, 5), "pure_toz": sa.Numeric(14, 6)}

    def table(name: str, *cols: str):
        return sa.table(name, *(sa.column(c, num[c]) if c in num else sa.column(c) for c in cols))

    details = table("set_details", "item_id", "country", "year", "mint_mark", "set_kind", "name")
    coins = table("set_coins", "item_id", "seq", "label", "quantity", "denomination", "year", "mint_mark", "series",
                  "composition", "weight_g", "metal", "fineness", "pure_toz", "composition_id")
    metal = table("item_metal_content", "item_id", "metal", "gross_weight_g", "fineness", "pure_toz", "source", "composition_id")
    rows = bind.execute(sa.text(
        "SELECT i.id, c.year, c.series FROM items i JOIN coin_details c ON c.item_id = i.id "
        "WHERE i.item_type = 'coin' AND c.denomination = 'set' AND c.year IS NOT NULL"
    )).all()
    for item_id, year, series in rows:
        content = bind.execute(sa.text(
            "SELECT m.source, k.key FROM item_metal_content m LEFT JOIN compositions k ON k.id = m.composition_id "
            "WHERE m.item_id = :id"), {"id": item_id}).all()
        # only a set still on its reference figure: one somebody adjusted by hand is left as it is
        if len(content) != 1 or content[0][0] != "reference" or not (content[0][1] or "").startswith("us-set-"):
            continue
        spec = mint_sets.contents(year, "silver_proof", quarters_only=(series or "").lower().startswith("quarters"))
        if spec is None:
            continue
        bind.execute(details.insert().values(item_id=item_id, country="United States", year=year, mint_mark=spec.mint_mark,
                                             set_kind=spec.kind, name=spec.name))
        gross = Decimal(0)
        for seq, c in enumerate(spec.coins):
            bind.execute(coins.insert().values(
                item_id=item_id, seq=seq, label=c.label, quantity=c.quantity, denomination=c.denomination, year=c.year,
                mint_mark=c.mint_mark, series=c.series, composition=c.composition, weight_g=c.weight_g, metal=c.metal,
                fineness=c.fineness, pure_toz=c.pure_toz, composition_id=None))
            if c.metal:
                gross += c.weight_g * c.quantity
        fine = {c.fineness for c in spec.coins if c.metal}
        bind.execute(metal.delete().where(metal.c.item_id == item_id))
        for m, oz in spec.pure_toz().items():
            bind.execute(metal.insert().values(item_id=item_id, metal=m, gross_weight_g=gross, pure_toz=oz, source="computed",
                                               fineness=next(iter(fine)) if len(fine) == 1 else None, composition_id=None))
        bind.execute(sa.text("DELETE FROM coin_details WHERE item_id = :id"), {"id": item_id})
        bind.execute(sa.text("UPDATE items SET item_type = 'set' WHERE id = :id"), {"id": item_id})


def downgrade() -> None:
    op.execute("DELETE FROM items WHERE item_type = 'set'")
    _item_type_check(OLD)
    op.drop_index(op.f("ix_set_coins_item_id"), table_name="set_coins")
    op.drop_table("set_coins")
    op.drop_table("set_details")
