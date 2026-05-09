"""normalize user auth emails

Revision ID: 0013_auth_email_normalization
Revises: 0012_chat_header_cols
Create Date: 2026-03-25 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_auth_email_normalization"
down_revision = "0012_chat_header_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_normalized", sa.String(length=255), nullable=True))

    op.execute("UPDATE users SET email_normalized = lower(btrim(email)) WHERE email IS NOT NULL")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM users
                GROUP BY business_id, email_normalized
                HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION 'Cannot apply auth normalization: duplicate normalized emails found per business_id.';
            END IF;
        END $$;
        """
    )

    op.alter_column("users", "email_normalized", nullable=False)
    op.drop_constraint("uq_admin_business_email", "users", type_="unique")
    op.create_unique_constraint(
        "uq_admin_business_email_normalized", "users", ["business_id", "email_normalized"]
    )
    op.create_index(op.f("ix_users_email_normalized"), "users", ["email_normalized"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_email_normalized"), table_name="users")
    op.drop_constraint("uq_admin_business_email_normalized", "users", type_="unique")
    op.create_unique_constraint("uq_admin_business_email", "users", ["business_id", "email"])
    op.drop_column("users", "email_normalized")
