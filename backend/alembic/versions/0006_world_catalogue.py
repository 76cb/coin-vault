"""The world catalogue: historic US, UK and Commonwealth, the Americas, Europe, Asia and world bullion.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table():
    return sa.table(
        "compositions",
        sa.column("key", sa.String), sa.column("owner_id", sa.Integer), sa.column("label", sa.String),
        sa.column("country", sa.String), sa.column("denomination", sa.String), sa.column("year_from", sa.Integer),
        sa.column("year_to", sa.Integer), sa.column("mint_marks", sa.JSON), sa.column("metal", sa.String),
        sa.column("fineness", sa.Numeric), sa.column("gross_weight_g", sa.Numeric), sa.column("pure_toz", sa.Numeric),
        sa.column("per_face_unit", sa.Boolean), sa.column("citation", sa.Text),
    )


def upgrade() -> None:
    from app.compositions_seed import ROWS_V4

    existing = {r[0] for r in op.get_bind().execute(sa.text("SELECT key FROM compositions"))}
    rows = [dict(r, owner_id=None) for r in ROWS_V4 if r["key"] not in existing]
    if rows:
        op.bulk_insert(_table(), rows)


def downgrade() -> None:
    from app.compositions_seed import ROWS_V4

    if ROWS_V4:
        keys = ", ".join(f"'{r['key']}'" for r in ROWS_V4)
        # only rows nobody uses; anything referenced by an item stays
        op.execute(
            f"DELETE FROM compositions WHERE owner_id IS NULL AND key IN ({keys}) "
            "AND id NOT IN (SELECT composition_id FROM item_metal_content WHERE composition_id IS NOT NULL) "
            "AND id NOT IN (SELECT composition_id FROM lot_details WHERE composition_id IS NOT NULL)"
        )
