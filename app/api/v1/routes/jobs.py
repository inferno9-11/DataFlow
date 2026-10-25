import uuid

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import get_current_user, get_job_service
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.job import (
    JobCreateRequest,
    JobDetailResponse,
    JobFilterParams,
    JobResponse,
)
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["Processing Jobs"])
settings = get_settings()


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a batch of records for asynchronous background processing",
)
async def submit_job(
    request: Request,
    payload: JobCreateRequest,
    current_user: User = Depends(get_current_user),
    job_service: JobService = Depends(get_job_service),
) -> JobResponse:
    client_ip = request.client.host if request.client else "unknown"
    await limiter.check_rate_limit(
        key=f"jobs_submit:{current_user.id}:{client_ip}",
        max_requests=settings.RATE_LIMIT_BULK_PER_MINUTE,
        window_seconds=60,
    )
    return await job_service.submit_job(current_user.id, payload)


@router.get(
    "",
    response_model=PaginatedResponse[JobResponse],
    summary="List processing jobs with status filters and pagination",
)
async def list_jobs(
    status: str | None = Query(
        None,
        description="Filter by job status: queued, running, completed, partially_failed, failed",
    ),
    job_type: str | None = Query(None, description="Filter by job type"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Page size"),
    current_user: User = Depends(get_current_user),
    job_service: JobService = Depends(get_job_service),
) -> PaginatedResponse[JobResponse]:
    filters = JobFilterParams(
        status=status,
        job_type=job_type,
        page=page,
        page_size=page_size,
    )
    return await job_service.list_jobs(current_user.id, filters)


@router.get(
    "/{job_id}",
    response_model=JobDetailResponse,
    summary="Retrieve processing job details and row-level error breakdown",
)
async def get_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    job_service: JobService = Depends(get_job_service),
) -> JobDetailResponse:
    return await job_service.get_job(job_id, current_user.id)


@router.post(
    "/{job_id}/retry",
    response_model=JobResponse,
    summary="Retry an eligible failed or partially failed processing job",
)
async def retry_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    job_service: JobService = Depends(get_job_service),
) -> JobResponse:
    return await job_service.retry_job(job_id, current_user.id)
