"""remove redundant operator settings constraint

Revision ID: 0011_operator_settings_cleanup
Revises: 0010_legal_publication
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_operator_settings_cleanup"
down_revision = "0010_legal_publication"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    constraints = {item.get("name") for item in sa.inspect(bind).get_unique_constraints("operator_settings")}
    if "uq_operator_settings_user_id" in constraints:
        with op.batch_alter_table("operator_settings") as batch:
            batch.drop_constraint("uq_operator_settings_user_id", type_="unique")


def downgrade() -> None:
    # The unique index remains the canonical one-profile invariant.
    pass
