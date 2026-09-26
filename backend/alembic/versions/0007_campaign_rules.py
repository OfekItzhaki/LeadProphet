"""add campaign decision rules

Revision ID: 0007_campaign_rules
Revises: 0006_icp_sequences_variants
Create Date: 2026-09-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_campaign_rules"
down_revision: Union[str, None] = "0006_icp_sequences_variants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("campaigns") as batch:
        batch.add_column(sa.Column("campaign_rules", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("campaigns") as batch:
        batch.drop_column("campaign_rules")
