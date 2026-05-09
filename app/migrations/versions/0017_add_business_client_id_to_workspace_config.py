"""add business_client_id to workspace_config

Revision ID: 0017_add_business_client_id_to_workspace_config
Revises: 0016_ws_bcid
Create Date: 2026-05-03 16:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_cfg_bcid"
down_revision = "0016_ws_bcid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workspace_config", sa.Column("business_client_id", sa.String(length=100), nullable=True))
    op.create_index(
        op.f("ix_workspace_config_business_client_id"),
        "workspace_config",
        ["business_client_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_workspace_config_business_client_id"), table_name="workspace_config")
    op.drop_column("workspace_config", "business_client_id")
