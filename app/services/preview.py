from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, GroceryItem, GroceryList, Household, HouseholdMember, User

PREVIEW_EMAIL = "preview@example.com"
PREVIEW_USER_NAME = "Preview User"
PREVIEW_HOUSEHOLD_NAME = "Preview Household"
PREVIEW_LIST_NAME = "Weekend Shop"
PREVIEW_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("Produce", "green"),
    ("Bakery", "orange"),
    ("Dairy", "blue"),
)
PREVIEW_ITEMS: tuple[dict[str, object], ...] = (
    {"name": "Bananas", "quantity_text": "6", "note": "For smoothies", "category": "Produce"},
    {
        "name": "Sourdough",
        "quantity_text": "1 loaf",
        "note": "Fresh if possible",
        "category": "Bakery",
    },
    {
        "name": "Greek yogurt",
        "quantity_text": "2 tubs",
        "note": "Plain",
        "category": "Dairy",
        "checked": True,
    },
)


async def ensure_preview_seed_data(db: AsyncSession) -> None:
    existing_user = await db.execute(select(User).where(User.email == PREVIEW_EMAIL))
    if existing_user.scalar_one_or_none() is not None:
        return

    user = User(
        email=PREVIEW_EMAIL,
        password_hash="",
        display_name=PREVIEW_USER_NAME,
    )
    db.add(user)
    await db.flush()

    household = Household(name=PREVIEW_HOUSEHOLD_NAME, owner_user_id=user.id)
    db.add(household)
    await db.flush()

    db.add(HouseholdMember(household_id=household.id, user_id=user.id, role="owner"))

    grocery_list = GroceryList(
        household_id=household.id,
        name=PREVIEW_LIST_NAME,
        created_by=user.id,
    )
    db.add(grocery_list)
    await db.flush()

    categories: dict[str, Category] = {}
    for index, (name, color) in enumerate(PREVIEW_CATEGORIES):
        category = Category(
            household_id=household.id,
            name=name,
            color=color,
            sort_order=index,
        )
        db.add(category)
        await db.flush()
        categories[name] = category

    for index, item_data in enumerate(PREVIEW_ITEMS):
        category_name = item_data.get("category")
        category = categories.get(str(category_name)) if category_name else None
        db.add(
            GroceryItem(
                list_id=grocery_list.id,
                name=str(item_data["name"]),
                quantity_text=item_data.get("quantity_text") and str(item_data["quantity_text"]),
                note=item_data.get("note") and str(item_data["note"]),
                category_id=category.id if category else None,
                checked=bool(item_data.get("checked", False)),
                sort_order=index,
                created_by=user.id,
                updated_by=user.id,
            )
        )

    await db.commit()


async def fetch_preview_context(db: AsyncSession) -> dict[str, object] | None:
    user_result = await db.execute(select(User).where(User.email == PREVIEW_EMAIL))
    user = user_result.scalar_one_or_none()
    if user is None:
        return None

    household_result = await db.execute(
        select(Household)
        .where(Household.owner_user_id == user.id)
        .order_by(Household.created_at.asc())
    )
    household = household_result.scalars().first()
    if household is None:
        return None

    list_result = await db.execute(
        select(GroceryList)
        .where(GroceryList.household_id == household.id)
        .order_by(GroceryList.created_at.asc())
    )
    grocery_list = list_result.scalars().first()
    if grocery_list is None:
        return None

    category_result = await db.execute(
        select(Category)
        .where(Category.household_id == household.id)
        .order_by(Category.sort_order.asc())
    )
    categories = list(category_result.scalars().all())

    item_result = await db.execute(
        select(GroceryItem)
        .where(GroceryItem.list_id == grocery_list.id)
        .order_by(GroceryItem.sort_order.asc())
    )
    items = list(item_result.scalars().all())

    category_names = {str(category.id): category.name for category in categories}
    checked_count = sum(1 for item in items if item.checked)

    return {
        "user": user,
        "household": household,
        "grocery_list": grocery_list,
        "categories": categories,
        "items": items,
        "checked_count": checked_count,
        "total_count": len(items),
        "category_names": category_names,
    }
