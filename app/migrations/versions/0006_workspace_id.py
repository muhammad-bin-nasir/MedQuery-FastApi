"""add workspace_id to business_admins

Revision ID: 0006_workspace_id
Revises: 0005_prompt_engineering
Create Date: 2026-03-14 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_workspace_id"
down_revision = "0005_prompt_engineering"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "business_admins",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("business_admins", "workspace_id")
