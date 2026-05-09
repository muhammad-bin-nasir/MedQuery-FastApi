import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_client_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255))

    workspaces = relationship("Workspace", back_populates="business", cascade="all, delete-orphan")
    admins = relationship(
        "BusinessAdmin",
        back_populates="business",
        cascade="all, delete-orphan",
        foreign_keys="BusinessAdmin.business_id",
    )
    admin = relationship("BusinessAdmin", foreign_keys=[admin_id], uselist=False)
