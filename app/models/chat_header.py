import uuid

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ChatHeader(Base):
    __tablename__ = "chat_headers"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "chat_id", name="uq_chat_headers_owner_chat_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[str] = mapped_column(String(255), index=True)
    chat_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255))
