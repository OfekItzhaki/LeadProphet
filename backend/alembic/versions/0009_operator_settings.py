"""operator settings

Revision ID: 0009_operator_settings
Revises: 0008_public_content
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_operator_settings"
down_revision = "0008_public_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operator_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_name", sa.String(120), nullable=False, server_default="LeadProphet"),
        sa.Column("support_email", sa.String(320), nullable=False, server_default=""),
        sa.Column("phone", sa.String(80)),
        sa.Column("city", sa.String(160)),
        sa.Column("timezone", sa.String(80), nullable=False, server_default="Asia/Jerusalem"),
        sa.Column("response_time", sa.String(160)),
        sa.Column("company_description", sa.Text()),
        sa.Column("footer_text", sa.String(500)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_operator_settings_user_id", "operator_settings", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_operator_settings_user_id", table_name="operator_settings")
    op.drop_table("operator_settings")
