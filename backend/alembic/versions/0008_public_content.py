"""add public content, legal documents, and contact messages

Revision ID: 0008_public_content
Revises: 0007_campaign_rules
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_public_content"
down_revision: Union[str, None] = "0007_campaign_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cms_content", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(120), nullable=False), sa.Column("body", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_cms_content_slug"),
    )
    op.create_table(
        "legal_documents", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_type", sa.String(40), nullable=False), sa.Column("version", sa.String(40), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_type", "version", name="uq_legal_document_version"),
    )
    op.create_index("ix_legal_documents_document_type", "legal_documents", ["document_type"])
    op.create_table(
        "contact_messages", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("email", sa.String(320), nullable=False),
        sa.Column("topic", sa.String(40), nullable=False), sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_contact_messages_user_id", "contact_messages", ["user_id"])
    op.create_index("ix_contact_messages_email", "contact_messages", ["email"])
    op.create_index("ix_contact_messages_status", "contact_messages", ["status"])
    op.create_index("ix_contact_messages_status_created", "contact_messages", ["status", "created_at"])


def downgrade() -> None:
    op.drop_table("contact_messages")
    op.drop_table("legal_documents")
    op.drop_table("cms_content")
