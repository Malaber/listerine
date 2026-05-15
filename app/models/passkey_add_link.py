import math
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class PasskeyAddLink(Base):
    __tablename__ = "passkey_add_links"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="passkey_add_links")

    @property
    def short_id(self) -> str:
        return str(self.id).split("-", maxsplit=1)[0]

    def is_active(self, *, now: datetime | None = None) -> bool:
        if self.used_at is not None:
            return False
        return _as_utc(self.expires_at) > (now or datetime.now(UTC))

    @property
    def remaining_hours(self) -> int:
        remaining = _as_utc(self.expires_at) - datetime.now(UTC)
        return max(1, math.ceil(remaining.total_seconds() / 3600))
