from decimal import Decimal

from pydantic import BaseModel


class AnalyticsSummaryResponse(BaseModel):
    total_records: int
    total_amount: Decimal
    currency_breakdown: dict[str, Decimal]
    status_breakdown: dict[str, int]
    category_breakdown: dict[str, int]
    average_risk_score: float
