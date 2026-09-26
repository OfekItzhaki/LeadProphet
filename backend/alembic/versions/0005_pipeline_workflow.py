"""add pipeline stages, tasks, notes, and outreach tracking

Revision ID: 0005_pipeline_workflow
Revises: 0004_lead_quality
Create Date: 2026-09-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_pipeline_workflow"
down_revision: Union[str, None] = "0004_lead_quality"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("leads") as batch_op:
        batch_op.add_column(sa.Column("pipeline_stage", sa.String(length=40), nullable=False, server_default="new"))
        batch_op.create_index("ix_leads_pipeline_stage", ["pipeline_stage"])

    with op.batch_alter_table("outreach_messages") as batch_op:
        batch_op.add_column(sa.Column("sent_via", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("sent_by_user_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("follow_up_due_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_outreach_messages_sent_by_user_id", "users", ["sent_by_user_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_index("ix_outreach_messages_follow_up_due_at", ["follow_up_due_at"])

    op.create_table(
        "lead_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("lead_id", sa.String(length=36), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lead_tasks_lead_id", "lead_tasks", ["lead_id"])
    op.create_index("ix_lead_tasks_user_id", "lead_tasks", ["user_id"])
    op.create_index("ix_lead_tasks_due_date", "lead_tasks", ["due_date"])
    op.create_index("ix_lead_tasks_user_due", "lead_tasks", ["user_id", "due_date", "completed_at"])

    op.create_table(
        "lead_notes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("lead_id", sa.String(length=36), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lead_notes_lead_id", "lead_notes", ["lead_id"])
    op.create_index("ix_lead_notes_user_id", "lead_notes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_lead_notes_user_id", table_name="lead_notes")
    op.drop_index("ix_lead_notes_lead_id", table_name="lead_notes")
    op.drop_table("lead_notes")
    op.drop_index("ix_lead_tasks_user_due", table_name="lead_tasks")
    op.drop_index("ix_lead_tasks_due_date", table_name="lead_tasks")
    op.drop_index("ix_lead_tasks_user_id", table_name="lead_tasks")
    op.drop_index("ix_lead_tasks_lead_id", table_name="lead_tasks")
    op.drop_table("lead_tasks")
    with op.batch_alter_table("outreach_messages") as batch_op:
        batch_op.drop_index("ix_outreach_messages_follow_up_due_at")
        batch_op.drop_constraint("fk_outreach_messages_sent_by_user_id", type_="foreignkey")
        batch_op.drop_column("follow_up_due_at")
        batch_op.drop_column("sent_by_user_id")
        batch_op.drop_column("sent_via")
    with op.batch_alter_table("leads") as batch_op:
        batch_op.drop_index("ix_leads_pipeline_stage")
        batch_op.drop_column("pipeline_stage")
