from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class HouseholdCreate(BaseModel):
    name: str


class HouseholdOut(ORMModel):
    id: UUID
    name: str


class GroceryListCreate(BaseModel):
    name: str


class GroceryListOut(ORMModel):
    id: UUID
    household_id: UUID
    name: str
    archived: bool


class CategoryCreate(BaseModel):
    name: str
    color: str | None = None
    aliases: list[str] = Field(default_factory=list)


class CategoryOut(ORMModel):
    id: UUID
    household_id: UUID | None
    name: str
    color: str | None
    aliases: list[str]


class ListCategoryOrderUpdate(BaseModel):
    category_ids: list[UUID]


class ListCategoryOrderOut(BaseModel):
    category_id: UUID
    sort_order: int


class GroceryItemCreate(BaseModel):
    name: str
    quantity_text: str | None = None
    note: str | None = None
    category_id: UUID | None = None
    sort_order: int = 0


class GroceryItemUpdate(BaseModel):
    name: str | None = None
    quantity_text: str | None = None
    note: str | None = None
    category_id: UUID | None = None
    sort_order: int | None = None


class GroceryItemOut(ORMModel):
    id: UUID
    list_id: UUID
    name: str
    quantity_text: str | None
    note: str | None
    category_id: UUID | None
    checked: bool
    checked_at: datetime | None
    sort_order: int
