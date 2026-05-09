"""add business_client_id to workspaces

Revision ID: 0016_add_business_client_id_to_workspaces
Revises: 0015_users_bcid
Create Date: 2026-05-03 16:05:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_ws_bcid"
down_revision = "0015_users_bcid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("business_client_id", sa.String(length=100), nullable=True))
    op.create_index(op.f("ix_workspaces_business_client_id"), "workspaces", ["business_client_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_workspaces_business_client_id"), table_name="workspaces")
    op.drop_column("workspaces", "business_client_id")
