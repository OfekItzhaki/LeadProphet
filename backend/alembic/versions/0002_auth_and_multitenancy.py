"""add users, refresh sessions, and row ownership

Revision ID: 0002_auth_multitenancy
Revises: 0001_initial
Create Date: 2026-09-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_auth_multitenancy"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_USER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("google_subject", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("avatar_url", sa.String(length=1000), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="owner"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("google_subject", name="uq_users_google_subject"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.execute(
        sa.text(
            "INSERT INTO users (id, email, display_name, role, is_active) "
            "VALUES (:id, :email, :name, 'owner', true)"
        ).bindparams(id=LEGACY_USER_ID, email="legacy@leadprophet.local", name="Legacy workspace")
    )

    ownership_tables = ("campaigns", "leads", "outreach_templates", "outreach_messages")
    for table in ownership_tables:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("user_id", sa.String(length=36), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET user_id = :user_id").bindparams(user_id=LEGACY_USER_ID))
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column("user_id", nullable=False)
            batch_op.create_foreign_key(f"fk_{table}_user_id", "users", ["user_id"], ["id"], ondelete="CASCADE")
            batch_op.create_index(f"ix_{table}_user_id", ["user_id"])

    with op.batch_alter_table("ai_call_logs") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key("fk_ai_call_logs_user_id", "users", ["user_id"], ["id"], ondelete="SET NULL")
        batch_op.create_index("ix_ai_call_logs_user_id", ["user_id"])
    op.execute(sa.text("UPDATE ai_call_logs SET user_id = :user_id").bindparams(user_id=LEGACY_USER_ID))

    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
    op.create_index("ix_campaigns_user_active", "campaigns", ["user_id", "is_active"])
    op.create_index("ix_leads_user_status", "leads", ["user_id", "status"])
    op.create_index("ix_leads_user_score", "leads", ["user_id", "score"])
    op.create_index("ix_leads_user_campaign", "leads", ["user_id", "campaign_id"])
    op.create_index("ix_outreach_user_campaign", "outreach_messages", ["user_id", "campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_outreach_user_campaign", table_name="outreach_messages")
    op.drop_index("ix_leads_user_campaign", table_name="leads")
    op.drop_index("ix_leads_user_score", table_name="leads")
    op.drop_index("ix_leads_user_status", table_name="leads")
    op.drop_index("ix_campaigns_user_active", table_name="campaigns")
    op.drop_index("ix_refresh_sessions_user_id", table_name="refresh_sessions")
    op.drop_table("refresh_sessions")

    with op.batch_alter_table("ai_call_logs") as batch_op:
        batch_op.drop_index("ix_ai_call_logs_user_id")
        batch_op.drop_constraint("fk_ai_call_logs_user_id", type_="foreignkey")
        batch_op.drop_column("user_id")
    for table in ("outreach_messages", "outreach_templates", "leads", "campaigns"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_index(f"ix_{table}_user_id")
            batch_op.drop_constraint(f"fk_{table}_user_id", type_="foreignkey")
            batch_op.drop_column("user_id")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
