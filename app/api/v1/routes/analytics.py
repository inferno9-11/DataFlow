from fastapi import APIRouter, Depends

from app.api.deps import get_analytics_service, get_current_user
from app.models.user import User
from app.schemas.analytics import AnalyticsSummaryResponse
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get(
    "/summary",
    response_model=AnalyticsSummaryResponse,
    summary="Get aggregated transaction volume, status distributions, and average risk metrics",
)
async def get_analytics_summary(
    current_user: User = Depends(get_current_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsSummaryResponse:
    return await analytics_service.get_summary(current_user.id)
