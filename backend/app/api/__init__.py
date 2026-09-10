from fastapi import APIRouter
from app.api.routes.documents import router as documents_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(documents_router)
