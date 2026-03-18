"""add chat_headers table

Revision ID: 0011_add_chat_headers_table
Revises: 0010_business_admin_id
Create Date: 2026-03-18 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0011_add_chat_headers_table"
down_revision = "0010_business_admin_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_headers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("chat_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "chat_id", name="uq_chat_headers_owner_chat_id"),
    )
    op.create_index(op.f("ix_chat_headers_owner_user_id"), "chat_headers", ["owner_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_headers_owner_user_id"), table_name="chat_headers")
    op.drop_table("chat_headers")
