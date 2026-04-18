import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class BusinessAdmin(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("business_id", "email_normalized", name="uq_admin_business_email_normalized"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=True
    )
    business_client_id: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(255))
    email_normalized: Mapped[str] = mapped_column(String(255), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="admin")

    business = relationship("Business", back_populates="admins", foreign_keys=[business_id])
