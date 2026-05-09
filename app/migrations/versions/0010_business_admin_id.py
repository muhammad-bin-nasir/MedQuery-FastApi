"""add admin_id to businesses

Revision ID: 0010_business_admin_id
Revises: 0009_admin_scope_unique
Create Date: 2026-03-14 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010_business_admin_id"
down_revision = "0009_admin_scope_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("businesses", sa.Column("admin_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "businesses_admin_id_fkey",
        "businesses",
        "users",
        ["admin_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("businesses_admin_id_fkey", "businesses", type_="foreignkey")
    op.drop_column("businesses", "admin_id")
