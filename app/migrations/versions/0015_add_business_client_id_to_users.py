"""add business_client_id to users

Revision ID: 0015_add_business_client_id_to_users
Revises: 0014_chat_ownership_uuid_scope
Create Date: 2026-05-03 15:54:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0015_users_bcid"
down_revision = "0014_chat_ownership_uuid_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("business_client_id", sa.String(length=100), nullable=True))
    op.create_index(op.f("ix_users_business_client_id"), "users", ["business_client_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_business_client_id"), table_name="users")
    op.drop_column("users", "business_client_id")
