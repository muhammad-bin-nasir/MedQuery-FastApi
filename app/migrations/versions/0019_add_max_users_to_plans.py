"""add max_users to plans

Revision ID: 0019_plans_max_users
Revises: 0018_plans_table
Create Date: 2026-07-14 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "0019_plans_max_users"
down_revision = "0018_plans_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("max_users", sa.Integer(), nullable=False, server_default="5"),
    )


def downgrade() -> None:
    op.drop_column("plans", "max_users")
