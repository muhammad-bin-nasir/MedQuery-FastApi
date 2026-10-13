"""add plans table

Revision ID: 0018_plans_table
Revises: 0017_cfg_bcid
Create Date: 2026-07-14 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0018_plans_table"
down_revision = "0017_cfg_bcid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_businesses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_workspaces", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_rag_documents", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_plans_code"), "plans", ["code"], unique=True)

    plans_table = sa.table(
        "plans",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("price_cents", sa.Integer),
        sa.column("max_businesses", sa.Integer),
        sa.column("max_workspaces", sa.Integer),
        sa.column("max_rag_documents", sa.Integer),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    import uuid
    from datetime import datetime

    op.bulk_insert(
        plans_table,
        [
            {
                "id": uuid.uuid4(),
                "code": "basic",
                "name": "Basic",
                "price_cents": 900,
                "max_businesses": 1,
                "max_workspaces": 3,
                "max_rag_documents": 50,
                "sort_order": 1,
                "is_active": True,
                "created_at": datetime.utcnow(),
            },
            {
                "id": uuid.uuid4(),
                "code": "plus",
                "name": "Plus",
                "price_cents": 1900,
                "max_businesses": 2,
                "max_workspaces": 8,
                "max_rag_documents": 200,
                "sort_order": 2,
                "is_active": True,
                "created_at": datetime.utcnow(),
            },
            {
                "id": uuid.uuid4(),
                "code": "pro",
                "name": "Pro",
                "price_cents": 4900,
                "max_businesses": 5,
                "max_workspaces": 20,
                "max_rag_documents": 1000,
                "sort_order": 3,
                "is_active": True,
                "created_at": datetime.utcnow(),
            },
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_plans_code"), table_name="plans")
    op.drop_table("plans")
