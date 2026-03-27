"""harden chat ownership with immutable user uuid and tenant scope

Revision ID: 0014_chat_ownership_uuid_scope
Revises: 0013_auth_email_normalization
Create Date: 2026-03-25 00:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0014_chat_ownership_uuid_scope"
down_revision = "0013_auth_email_normalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_requests", sa.Column("user_uuid", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_chat_requests_user_uuid"), "chat_requests", ["user_uuid"], unique=False)
    op.create_foreign_key(
        "fk_chat_requests_user_uuid_users",
        "chat_requests",
        "users",
        ["user_uuid"],
        ["id"],
    )

    op.add_column("chat_headers", sa.Column("owner_user_uuid", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("chat_headers", sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("chat_headers", sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.create_index(op.f("ix_chat_headers_owner_user_uuid"), "chat_headers", ["owner_user_uuid"], unique=False)
    op.create_index(op.f("ix_chat_headers_business_id"), "chat_headers", ["business_id"], unique=False)
    op.create_index(op.f("ix_chat_headers_workspace_id"), "chat_headers", ["workspace_id"], unique=False)

    op.execute(
        """
        UPDATE chat_requests cr
        SET user_uuid = u.id
        FROM users u
        WHERE cr.user_uuid IS NULL
          AND u.email_normalized = lower(btrim(cr.user_id));
        """
    )

    op.execute(
        """
        WITH latest_request AS (
            SELECT
                cr.chat_header,
                cr.business_id,
                cr.workspace_id,
                cr.user_uuid,
                ROW_NUMBER() OVER (
                    PARTITION BY cr.chat_header
                    ORDER BY cr.created_at DESC NULLS LAST, cr.id DESC
                ) AS rn
            FROM chat_requests cr
            WHERE cr.chat_header IS NOT NULL
              AND cr.user_uuid IS NOT NULL
        )
        UPDATE chat_headers ch
        SET
            owner_user_uuid = lr.user_uuid,
            business_id = lr.business_id,
            workspace_id = lr.workspace_id
        FROM latest_request lr
        WHERE ch.chat_id = lr.chat_header
          AND lr.rn = 1
          AND ch.owner_user_uuid IS NULL;
        """
    )

    op.create_unique_constraint(
        "uq_chat_headers_owner_scope_chat_id",
        "chat_headers",
        ["owner_user_uuid", "business_id", "workspace_id", "chat_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_chat_headers_owner_scope_chat_id", "chat_headers", type_="unique")

    op.drop_index(op.f("ix_chat_headers_workspace_id"), table_name="chat_headers")
    op.drop_index(op.f("ix_chat_headers_business_id"), table_name="chat_headers")
    op.drop_index(op.f("ix_chat_headers_owner_user_uuid"), table_name="chat_headers")

    op.drop_column("chat_headers", "workspace_id")
    op.drop_column("chat_headers", "business_id")
    op.drop_column("chat_headers", "owner_user_uuid")

    op.drop_constraint("fk_chat_requests_user_uuid_users", "chat_requests", type_="foreignkey")
    op.drop_index(op.f("ix_chat_requests_user_uuid"), table_name="chat_requests")
    op.drop_column("chat_requests", "user_uuid")
