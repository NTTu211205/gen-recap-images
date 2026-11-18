# Aggregate the implemented version-one API routes.

from fastapi import APIRouter

from src.api.v1.endpoints.health import router as health_router
from src.api.v1.endpoints.recap import router as recap_router

api_router = APIRouter(prefix="/v1")
api_router.include_router(health_router)
api_router.include_router(recap_router)
