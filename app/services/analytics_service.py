import uuid

from app.repositories.record_repository import RecordRepository
from app.schemas.analytics import AnalyticsSummaryResponse


class AnalyticsService:
    def __init__(self, record_repo: RecordRepository):
        self.record_repo = record_repo

    async def get_summary(self, user_id: uuid.UUID) -> AnalyticsSummaryResponse:
        summary_data = await self.record_repo.get_analytics_summary(user_id)
        return AnalyticsSummaryResponse(
            total_records=summary_data["total_records"],
            total_amount=summary_data["total_amount"],
            currency_breakdown=summary_data["currency_breakdown"],
            status_breakdown=summary_data["status_breakdown"],
            category_breakdown=summary_data["category_breakdown"],
            average_risk_score=summary_data["average_risk_score"],
        )
