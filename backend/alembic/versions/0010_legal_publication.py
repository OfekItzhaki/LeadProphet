"""legal publication state

Revision ID: 0010_legal_publication
Revises: 0009_operator_settings
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_legal_publication"
down_revision = "0009_operator_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("legal_documents", sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("legal_documents", "is_published")
