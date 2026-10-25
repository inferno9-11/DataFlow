import redis.asyncio as aioredis
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.config import get_settings
from app.core.metrics import get_latest_metrics
from app.db.session import async_session_factory
from app.schemas.health import HealthLiveResponse, HealthReadyResponse

router = APIRouter(tags=["Operations"])
settings = get_settings()


@router.get(
    "/health/live",
    response_model=HealthLiveResponse,
    summary="Liveness probe for container orchestrators",
)
async def liveness_probe() -> HealthLiveResponse:
    return HealthLiveResponse(
        status="alive",
        environment=settings.ENVIRONMENT,
        version=settings.APP_VERSION,
    )


@router.get(
    "/health/ready",
    response_model=HealthReadyResponse,
    summary="Readiness probe verifying database and message broker availability",
)
async def readiness_probe(response: Response) -> HealthReadyResponse:
    deps = {"database": "unknown", "redis": "unknown"}
    details = {}
    is_ready = True

    # 1. Check Database
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
            deps["database"] = "connected"
    except Exception as e:
        deps["database"] = "disconnected"
        details["database_error"] = str(e)
        is_ready = False

    # 2. Check Redis
    try:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )
        await redis_client.ping()
        await redis_client.aclose()
        deps["redis"] = "connected"
    except Exception as e:
        deps["redis"] = "disconnected"
        details["redis_error"] = str(e)
        # Redis disconnection marks service degraded, but database is critical
        if is_ready:
            deps["status_note"] = "Running in degraded mode (background queue unavailable)"

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall_status = "not_ready"
    elif deps["redis"] != "connected":
        overall_status = "degraded"
    else:
        overall_status = "ready"

    return HealthReadyResponse(
        status=overall_status,
        environment=settings.ENVIRONMENT,
        version=settings.APP_VERSION,
        dependencies=deps,
        details=details if details else None,
    )


@router.get(
    "/metrics",
    summary="Prometheus-compatible operational metrics scrape endpoint",
)
async def metrics_endpoint() -> Response:
    content, content_type = get_latest_metrics()
    return Response(content=content, media_type=content_type)
