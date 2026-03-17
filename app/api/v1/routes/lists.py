from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_household_member, get_current_user, get_list_for_user
from app.core.database import get_db
from app.models import GroceryList, User
from app.schemas.domain import GroceryListCreate, GroceryListOut

router = APIRouter(tags=["lists"])


@router.post("/households/{household_id}/lists", response_model=GroceryListOut)
async def create_list(
    household_id: UUID,
    payload: GroceryListCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroceryList:
    await ensure_household_member(db, household_id, user.id)
    grocery_list = GroceryList(household_id=household_id, name=payload.name, created_by=user.id)
    db.add(grocery_list)
    await db.commit()
    await db.refresh(grocery_list)
    return grocery_list


@router.get("/households/{household_id}/lists", response_model=list[GroceryListOut])
async def list_lists(
    household_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GroceryList]:
    await ensure_household_member(db, household_id, user.id)
    result = await db.execute(select(GroceryList).where(GroceryList.household_id == household_id))
    return list(result.scalars().all())


@router.get("/lists/{list_id}", response_model=GroceryListOut)
async def get_list(
    list_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> GroceryList:
    return await get_list_for_user(db, list_id, user.id)


@router.delete("/lists/{list_id}")
async def delete_list(
    list_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    grocery_list = await get_list_for_user(db, list_id, user.id)
    await db.delete(grocery_list)
    await db.commit()
    return {"message": "deleted"}


@router.patch("/lists/{list_id}", response_model=GroceryListOut)
async def patch_list(
    list_id: UUID,
    payload: GroceryListCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroceryList:
    grocery_list = await get_list_for_user(db, list_id, user.id)
    if not payload.name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    grocery_list.name = payload.name
    await db.commit()
    await db.refresh(grocery_list)
    return grocery_list
