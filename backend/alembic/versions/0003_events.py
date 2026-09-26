"""add structured events

Revision ID: 0003_events
Revises: 0002_auth_multitenancy
Create Date: 2026-09-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_events"
down_revision: Union[str, None] = "0002_auth_multitenancy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lead_id", sa.String(length=36), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_events_user_id", "events", ["user_id"])
    op.create_index("ix_events_campaign_id", "events", ["campaign_id"])
    op.create_index("ix_events_lead_id", "events", ["lead_id"])
    op.create_index("ix_events_event_type", "events", ["event_type"])
    op.create_index("ix_events_user_created", "events", ["user_id", "created_at"])
    op.create_index("ix_events_campaign_type", "events", ["campaign_id", "event_type"])


def downgrade() -> None:
    op.drop_index("ix_events_campaign_type", table_name="events")
    op.drop_index("ix_events_user_created", table_name="events")
    op.drop_index("ix_events_event_type", table_name="events")
    op.drop_index("ix_events_lead_id", table_name="events")
    op.drop_index("ix_events_campaign_id", table_name="events")
    op.drop_index("ix_events_user_id", table_name="events")
    op.drop_table("events")
