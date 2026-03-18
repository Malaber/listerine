from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Category,
    GroceryItem,
    GroceryList,
    Household,
    HouseholdMember,
    ListCategoryOrder,
    User,
)

PREVIEW_EMAIL = "preview@example.com"
PREVIEW_USER_NAME = "Preview User"
PREVIEW_HOUSEHOLD_NAME = "Preview Household"
PREVIEW_LIST_NAME = "Weekend Shop"
UI_E2E_LIST_NAME = "Browser Test Shop"
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
UI_E2E_CATEGORIES: tuple[dict[str, object], ...] = (
    {"name": "Konserven", "color": "#94a3b8", "aliases": ["Dose"]},
    {"name": "Milch & Eier", "color": "#d8b4e2", "aliases": ["Molkerei"]},
    {"name": "Nudeln", "color": "#d6b08b", "aliases": ["Pasta"]},
    {"name": "Reinigung", "color": "#c026a3", "aliases": ["Putzen"]},
    {"name": "Tiefkuehlkost", "color": "#4dd0e1", "aliases": ["TK"]},
    {"name": "Vegan", "color": "#00b512", "aliases": ["Plant based"]},
    {"name": "Backwaren", "color": "#fb923c", "aliases": ["Brot", "Broetchen", "Baeckerei"]},
    {"name": "Backzutaten", "color": "#ec4899", "aliases": ["backen"]},
    {"name": "Fleisch", "color": "#ef4444", "aliases": ["Metzger"]},
    {"name": "Gemuese", "color": "#7ed957", "aliases": ["Gruenzeug"]},
)
UI_E2E_ITEMS: tuple[dict[str, object], ...] = (
    {"name": "Loose item", "quantity_text": "1"},
    {"name": "Spaghetti", "category": "Nudeln", "quantity_text": "2 packs"},
    {"name": "Brot", "category": "Backwaren", "note": "Seeded checked duplicate", "checked": True},
    {"name": "Tomaten", "category": "Konserven"},
    {"name": "Eier", "category": "Milch & Eier", "quantity_text": "10"},
    {"name": "Putzmittel", "category": "Reinigung"},
    {"name": "Erbsen", "category": "Tiefkuehlkost"},
    {"name": "Tofu", "category": "Vegan"},
    {"name": "Mehl", "category": "Backzutaten"},
    {"name": "Hackfleisch", "category": "Fleisch"},
    {"name": "Paprika", "category": "Gemuese"},
)
UI_E2E_CATEGORY_ORDER: tuple[str, ...] = (
    "Konserven",
    "Milch & Eier",
    "Nudeln",
    "Reinigung",
    "Tiefkuehlkost",
    "Vegan",
    "Backwaren",
    "Backzutaten",
    "Fleisch",
    "Gemuese",
)


async def _get_preview_user(db: AsyncSession) -> User | None:
    existing_user = await db.execute(select(User).where(User.email == PREVIEW_EMAIL))
    return existing_user.scalar_one_or_none()


async def _ensure_preview_user_and_household(db: AsyncSession) -> tuple[User, Household]:
    user = await _get_preview_user(db)
    if user is None:
        user = User(
            email=PREVIEW_EMAIL,
            password_hash="",
            display_name=PREVIEW_USER_NAME,
            is_admin=True,
        )
        db.add(user)
        await db.flush()
    elif not user.is_admin:
        user.is_admin = True
        await db.flush()

    household_result = await db.execute(
        select(Household)
        .where(Household.owner_user_id == user.id)
        .order_by(Household.created_at.asc())
    )
    household = household_result.scalars().first()
    if household is None:
        household = Household(name=PREVIEW_HOUSEHOLD_NAME, owner_user_id=user.id)
        db.add(household)
        await db.flush()
        db.add(HouseholdMember(household_id=household.id, user_id=user.id, role="owner"))
        await db.flush()

    return user, household


async def _ensure_global_category(
    db: AsyncSession, *, name: str, color: str | None, aliases: list[str] | None = None
) -> Category:
    result = await db.execute(select(Category).where(Category.name == name))
    category = result.scalar_one_or_none()
    if category is None:
        category = Category(household_id=None, name=name, color=color)
        db.add(category)
    else:
        category.color = color
    category.aliases = aliases or []
    await db.flush()
    return category


async def _ensure_list(
    db: AsyncSession, *, household: Household, user: User, name: str
) -> GroceryList:
    result = await db.execute(
        select(GroceryList).where(
            GroceryList.household_id == household.id,
            GroceryList.name == name,
        )
    )
    grocery_list = result.scalar_one_or_none()
    if grocery_list is None:
        grocery_list = GroceryList(
            household_id=household.id,
            name=name,
            created_by=user.id,
        )
        db.add(grocery_list)
        await db.flush()
    return grocery_list


async def ensure_preview_seed_data(db: AsyncSession) -> None:
    user, household = await _ensure_preview_user_and_household(db)
    grocery_list = await _ensure_list(db, household=household, user=user, name=PREVIEW_LIST_NAME)

    existing_items = await db.execute(
        select(GroceryItem.id).where(GroceryItem.list_id == grocery_list.id)
    )
    if existing_items.scalars().first() is not None:
        await db.commit()
        return

    categories: dict[str, Category] = {}
    for name, color in PREVIEW_CATEGORIES:
        category = await _ensure_global_category(db, name=name, color=color, aliases=[])
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


async def ensure_ui_e2e_seed_data(db: AsyncSession) -> None:
    user, household = await _ensure_preview_user_and_household(db)
    grocery_list = await _ensure_list(db, household=household, user=user, name=UI_E2E_LIST_NAME)

    categories: dict[str, Category] = {}
    for category_data in UI_E2E_CATEGORIES:
        category = await _ensure_global_category(
            db,
            name=str(category_data["name"]),
            color=category_data.get("color") and str(category_data["color"]),
            aliases=[str(alias) for alias in category_data.get("aliases", [])],
        )
        categories[category.name] = category

    existing_items_result = await db.execute(
        select(GroceryItem).where(GroceryItem.list_id == grocery_list.id)
    )
    existing_items = {item.name: item for item in existing_items_result.scalars().all()}

    for index, item_data in enumerate(UI_E2E_ITEMS):
        category_name = item_data.get("category")
        category = categories.get(str(category_name)) if category_name else None
        item = existing_items.get(str(item_data["name"]))
        if item is None:
            item = GroceryItem(
                list_id=grocery_list.id,
                name=str(item_data["name"]),
                created_by=user.id,
                updated_by=user.id,
            )
            db.add(item)

        item.quantity_text = item_data.get("quantity_text") and str(item_data["quantity_text"])
        item.note = item_data.get("note") and str(item_data["note"])
        item.category_id = category.id if category else None
        item.checked = bool(item_data.get("checked", False))
        item.sort_order = index
        item.updated_by = user.id
        if item.checked:
            item.checked_by = user.id
        else:
            item.checked_at = None
            item.checked_by = None

    await db.execute(delete(ListCategoryOrder).where(ListCategoryOrder.list_id == grocery_list.id))
    await db.flush()
    for index, category_name in enumerate(UI_E2E_CATEGORY_ORDER):
        db.add(
            ListCategoryOrder(
                list_id=grocery_list.id,
                category_id=categories[category_name].id,
                sort_order=index,
            )
        )

    await db.commit()


async def fetch_ui_e2e_context(db: AsyncSession) -> dict[str, object] | None:
    user = await _get_preview_user(db)
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
        select(GroceryList).where(
            GroceryList.household_id == household.id, GroceryList.name == UI_E2E_LIST_NAME
        )
    )
    grocery_list = list_result.scalar_one_or_none()
    if grocery_list is None:
        return None

    category_result = await db.execute(select(Category).order_by(Category.name.asc()))
    categories = list(category_result.scalars().all())
    item_result = await db.execute(
        select(GroceryItem)
        .where(GroceryItem.list_id == grocery_list.id)
        .order_by(GroceryItem.sort_order.asc())
    )
    items = list(item_result.scalars().all())
    order_result = await db.execute(
        select(ListCategoryOrder)
        .where(ListCategoryOrder.list_id == grocery_list.id)
        .order_by(ListCategoryOrder.sort_order.asc())
    )

    return {
        "user": user,
        "household": household,
        "grocery_list": grocery_list,
        "categories": categories,
        "items": items,
        "category_order": list(order_result.scalars().all()),
    }


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

    category_result = await db.execute(select(Category).order_by(Category.name.asc()))
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
