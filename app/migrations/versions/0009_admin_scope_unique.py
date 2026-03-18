"""enforce one admin per business/workspace

Revision ID: 0009_admin_scope_unique
Revises: 0008_users_table
Create Date: 2026-03-14 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_admin_scope_unique"
down_revision = "0008_users_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_users_admin_business_workspace",
        "users",
        ["business_id", "workspace_id"],
        unique=True,
        postgresql_where=sa.text("role = 'admin' AND workspace_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_admin_business_workspace", table_name="users")
