import uuid

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Plan(Base):
    """A subscription package tier, editable by super admins."""

    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_businesses: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_workspaces: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_rag_documents: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
