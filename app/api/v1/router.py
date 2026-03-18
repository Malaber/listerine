from fastapi import APIRouter

from app.api.v1.routes import auth, categories, households, items, lists, ws_lists

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(households.router)
api_router.include_router(lists.router)
api_router.include_router(categories.router)
api_router.include_router(items.router)
api_router.include_router(ws_lists.router)
