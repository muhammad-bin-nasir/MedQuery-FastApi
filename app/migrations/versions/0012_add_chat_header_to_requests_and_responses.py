"""add chat_header to chat request and response tables

Revision ID: 0012_chat_header_cols
Revises: 0011_add_chat_headers_table
Create Date: 2026-03-18 00:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_chat_header_cols"
down_revision = "0011_add_chat_headers_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_requests", sa.Column("chat_header", sa.String(length=255), nullable=True))
    op.add_column("chat_responses", sa.Column("chat_header", sa.String(length=255), nullable=True))
    op.create_index("ix_chat_requests_chat_header", "chat_requests", ["chat_header"], unique=False)
    op.create_index("ix_chat_responses_chat_header", "chat_responses", ["chat_header"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chat_responses_chat_header", table_name="chat_responses")
    op.drop_index("ix_chat_requests_chat_header", table_name="chat_requests")
    op.drop_column("chat_responses", "chat_header")
    op.drop_column("chat_requests", "chat_header")
