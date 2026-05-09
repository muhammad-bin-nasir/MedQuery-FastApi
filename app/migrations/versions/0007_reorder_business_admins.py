"""reorder business_admins columns to place workspace_id before timestamps

Revision ID: 0007_reorder_business_admins
Revises: 0006_workspace_id
Create Date: 2026-03-14 00:00:00
"""

from alembic import op


revision = "0007_reorder_business_admins"
down_revision = "0006_workspace_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL does not support altering column position directly.
    # Recreate table with the desired column order and copy data.
    op.execute(
        """
        CREATE TABLE business_admins_new (
            id UUID PRIMARY KEY,
            business_id UUID REFERENCES businesses(id),
            email VARCHAR(255) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL,
            workspace_id UUID REFERENCES workspaces(id),
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ,
            CONSTRAINT uq_admin_business_email_new UNIQUE (business_id, email)
        )
        """
    )

    op.execute(
        """
        INSERT INTO business_admins_new (
            id, business_id, email, password_hash, role, workspace_id, created_at, updated_at
        )
        SELECT
            id, business_id, email, password_hash, role, workspace_id, created_at, updated_at
        FROM business_admins
        """
    )

    op.execute("DROP TABLE business_admins")
    op.execute("ALTER TABLE business_admins_new RENAME TO business_admins")
    op.execute(
        "ALTER TABLE business_admins RENAME CONSTRAINT uq_admin_business_email_new TO uq_admin_business_email"
    )


def downgrade() -> None:
    # Restore previous physical order where workspace_id was at the end.
    op.execute(
        """
        CREATE TABLE business_admins_old (
            id UUID PRIMARY KEY,
            business_id UUID REFERENCES businesses(id),
            email VARCHAR(255) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ,
            workspace_id UUID REFERENCES workspaces(id),
            CONSTRAINT uq_admin_business_email_old UNIQUE (business_id, email)
        )
        """
    )

    op.execute(
        """
        INSERT INTO business_admins_old (
            id, business_id, email, password_hash, role, created_at, updated_at, workspace_id
        )
        SELECT
            id, business_id, email, password_hash, role, created_at, updated_at, workspace_id
        FROM business_admins
        """
    )

    op.execute("DROP TABLE business_admins")
    op.execute("ALTER TABLE business_admins_old RENAME TO business_admins")
    op.execute(
        "ALTER TABLE business_admins RENAME CONSTRAINT uq_admin_business_email_old TO uq_admin_business_email"
    )
