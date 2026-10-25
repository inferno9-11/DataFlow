from fastapi import APIRouter

from app.api.v1.routes.analytics import router as analytics_router
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.jobs import router as jobs_router
from app.api.v1.routes.records import router as records_router

api_v1_router = APIRouter()

api_v1_router.include_router(auth_router)
api_v1_router.include_router(records_router)
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(analytics_router)
