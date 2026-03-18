import uuid

from sqlalchemy import ForeignKey, Integer, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ListCategoryOrder(Base):
    __tablename__ = "list_category_orders"
    __table_args__ = (
        UniqueConstraint("list_id", "category_id", name="uq_list_category_orders_list_category"),
        UniqueConstraint("list_id", "sort_order", name="uq_list_category_orders_list_sort_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    list_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("grocery_lists.id"), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("categories.id"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
