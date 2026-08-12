"""add chat_headers and chat_id columns with soft delete

Revision ID: 0006_chat_headers
Revises: 0005_prompt_engineering
Create Date: 2026-07-28 15:55:00

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_chat_headers"
down_revision = "0005_prompt_engineering"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_headers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("owner_user_id", sa.String(255), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("chat_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False, server_default="New chat"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_chat_headers_owner_user_id", "chat_headers", ["owner_user_id"])
    op.create_index("ix_chat_headers_business_id", "chat_headers", ["business_id"])
    op.create_index("ix_chat_headers_workspace_id", "chat_headers", ["workspace_id"])
    op.create_index("ix_chat_headers_chat_id", "chat_headers", ["chat_id"])
    op.create_unique_constraint(
        "uq_chat_headers_owner_scope_chat_id",
        "chat_headers",
        ["owner_user_id", "business_id", "workspace_id", "chat_id"],
    )

    op.add_column("chat_requests", sa.Column("chat_header", sa.String(255), nullable=True))
    op.create_index("ix_chat_requests_chat_header", "chat_requests", ["chat_header"])

    op.add_column("chat_responses", sa.Column("chat_header", sa.String(255), nullable=True))
    op.create_index("ix_chat_responses_chat_header", "chat_responses", ["chat_header"])


def downgrade() -> None:
    op.drop_index("ix_chat_responses_chat_header", table_name="chat_responses")
    op.drop_column("chat_responses", "chat_header")

    op.drop_index("ix_chat_requests_chat_header", table_name="chat_requests")
    op.drop_column("chat_requests", "chat_header")

    op.drop_constraint("uq_chat_headers_owner_scope_chat_id", "chat_headers", type_="unique")
    op.drop_index("ix_chat_headers_chat_id", table_name="chat_headers")
    op.drop_index("ix_chat_headers_workspace_id", table_name="chat_headers")
    op.drop_index("ix_chat_headers_business_id", table_name="chat_headers")
    op.drop_index("ix_chat_headers_owner_user_id", table_name="chat_headers")
    op.drop_table("chat_headers")
