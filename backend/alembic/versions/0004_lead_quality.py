"""add lead deduplication and enrichment

Revision ID: 0004_lead_quality
Revises: 0003_events
Create Date: 2026-09-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_lead_quality"
down_revision: Union[str, None] = "0003_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("leads") as batch_op:
        batch_op.add_column(sa.Column("duplicate_of_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("enrichment", sa.JSON(), nullable=False, server_default="{}"))
        batch_op.create_foreign_key(
            "fk_leads_duplicate_of_id", "leads", ["duplicate_of_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_index("ix_leads_duplicate_of_id", ["duplicate_of_id"])
        batch_op.create_index(
            "ix_leads_user_campaign_duplicate", ["user_id", "campaign_id", "duplicate_of_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("leads") as batch_op:
        batch_op.drop_index("ix_leads_user_campaign_duplicate")
        batch_op.drop_index("ix_leads_duplicate_of_id")
        batch_op.drop_constraint("fk_leads_duplicate_of_id", type_="foreignkey")
        batch_op.drop_column("enrichment")
        batch_op.drop_column("duplicate_of_id")
