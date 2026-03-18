"""rename business_admins table to users

Revision ID: 0008_users_table
Revises: 0007_reorder_business_admins
Create Date: 2026-03-14 00:00:00
"""

from alembic import op


revision = "0008_users_table"
down_revision = "0007_reorder_business_admins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("business_admins", "users")


def downgrade() -> None:
    op.rename_table("users", "business_admins")
