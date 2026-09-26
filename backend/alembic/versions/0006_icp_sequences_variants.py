"""add ICP fields, sequences, and messaging variants

Revision ID: 0006_icp_sequences_variants
Revises: 0005_pipeline_workflow
Create Date: 2026-09-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_icp_sequences_variants"
down_revision: Union[str, None] = "0005_pipeline_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("campaigns") as batch:
        for name, default in (("icp_firmographics", "{}"), ("icp_technographics", "{}"), ("icp_pains", "[]"), ("icp_triggers", "[]"), ("icp_personas", "[]")):
            batch.add_column(sa.Column(name, sa.JSON(), nullable=False, server_default=default))
    op.create_table(
        "sequences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sequences_campaign_id", "sequences", ["campaign_id"])
    op.create_index("ix_sequences_user_id", "sequences", ["user_id"])
    op.create_index("ix_sequences_user_campaign", "sequences", ["user_id", "campaign_id"])
    op.create_table(
        "sequence_steps", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sequence_id", sa.String(36), sa.ForeignKey("sequences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False), sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("offset_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("template_ref", sa.String(255)), sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("sequence_id", "order_index", name="uq_sequence_step_order"),
    )
    op.create_index("ix_sequence_steps_sequence_id", "sequence_steps", ["sequence_id"])
    op.create_table(
        "message_variants", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_id", sa.String(36), sa.ForeignKey("sequences.id", ondelete="CASCADE")),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(40), nullable=False), sa.Column("variant_key", sa.String(40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_message_variants_campaign_id", "message_variants", ["campaign_id"])
    op.create_index("ix_message_variants_sequence_id", "message_variants", ["sequence_id"])
    op.create_index("ix_message_variants_user_id", "message_variants", ["user_id"])
    op.create_index("ix_variants_campaign_channel_key", "message_variants", ["campaign_id", "channel", "variant_key"])
    with op.batch_alter_table("leads") as batch:
        batch.add_column(sa.Column("sequence_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("sequence_position", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_leads_sequence_id", "sequences", ["sequence_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_leads_sequence_id", ["sequence_id"])
    with op.batch_alter_table("outreach_messages") as batch:
        batch.add_column(sa.Column("sequence_step_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("variant_ids", sa.JSON(), nullable=False, server_default="[]"))
        batch.create_foreign_key("fk_outreach_sequence_step_id", "sequence_steps", ["sequence_step_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_outreach_messages_sequence_step_id", ["sequence_step_id"])


def downgrade() -> None:
    with op.batch_alter_table("outreach_messages") as batch:
        batch.drop_index("ix_outreach_messages_sequence_step_id"); batch.drop_constraint("fk_outreach_sequence_step_id", type_="foreignkey")
        batch.drop_column("variant_ids"); batch.drop_column("sequence_step_id")
    with op.batch_alter_table("leads") as batch:
        batch.drop_index("ix_leads_sequence_id"); batch.drop_constraint("fk_leads_sequence_id", type_="foreignkey")
        batch.drop_column("sequence_position"); batch.drop_column("sequence_id")
    op.drop_table("message_variants"); op.drop_table("sequence_steps"); op.drop_table("sequences")
    with op.batch_alter_table("campaigns") as batch:
        for name in ("icp_personas", "icp_triggers", "icp_pains", "icp_technographics", "icp_firmographics"):
            batch.drop_column(name)
