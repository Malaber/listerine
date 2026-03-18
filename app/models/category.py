import uuid

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("households.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    color: Mapped[str | None] = mapped_column(String(30), nullable=True)
    aliases_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    @property
    def aliases(self) -> list[str]:
        return [alias.strip() for alias in self.aliases_text.splitlines() if alias.strip()]

    @aliases.setter
    def aliases(self, value: list[str]) -> None:
        self.aliases_text = "\n".join(alias.strip() for alias in value if alias.strip())
