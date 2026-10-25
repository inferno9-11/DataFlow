from pydantic import BaseModel


class HealthLiveResponse(BaseModel):
    status: str = "alive"
    environment: str
    version: str


class HealthReadyResponse(BaseModel):
    status: str  # "ready" or "degraded" or "not_ready"
    environment: str
    version: str
    dependencies: dict[str, str]  # {"database": "connected", "redis": "connected"}
    details: dict[str, str] | None = None
