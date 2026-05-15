import uuid

from sqlalchemy import ForeignKey, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ListDisabledCategory(Base):
    __tablename__ = "list_disabled_categories"
    __table_args__ = (
        UniqueConstraint(
            "list_id",
            "category_id",
            name="uq_list_disabled_categories_list_category",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    list_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("grocery_lists.id"), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("categories.id"), nullable=False
    )
