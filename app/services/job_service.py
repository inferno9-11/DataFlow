import uuid

from app.core.config import get_settings
from app.core.errors import BadRequestError, NotFoundError
from app.models.job import ProcessingJob
from app.repositories.job_repository import JobRepository
from app.schemas.common import PaginatedResponse
from app.schemas.job import (
    JobCreateRequest,
    JobDetailResponse,
    JobFilterParams,
    JobItemErrorResponse,
    JobResponse,
)
from app.workers.tasks import dispatch_job

settings = get_settings()


class JobService:
    def __init__(self, job_repo: JobRepository):
        self.job_repo = job_repo

    async def submit_job(self, user_id: uuid.UUID, payload: JobCreateRequest) -> JobResponse:
        # Check idempotency
        if payload.idempotency_key:
            existing = await self.job_repo.get_by_idempotency_key(payload.idempotency_key, user_id)
            if existing:
                return JobResponse.model_validate(existing)

        job = ProcessingJob(
            user_id=user_id,
            job_type=payload.job_type,
            status="queued",
            total_records=len(payload.records),
            processed_records=0,
            failed_records=0,
            retry_count=0,
            max_retries=settings.JOB_MAX_RETRIES,
            idempotency_key=payload.idempotency_key,
            payload_records=payload.records,
        )

        saved = await self.job_repo.create(job)

        # Dispatch task to background worker
        dispatch_job(saved.id)

        return JobResponse.model_validate(saved)

    async def get_job(self, job_id: uuid.UUID, user_id: uuid.UUID) -> JobDetailResponse:
        job = await self.job_repo.get_by_id(job_id, user_id, include_errors=True)
        if not job:
            raise NotFoundError("Job", job_id)

        error_items = [JobItemErrorResponse.model_validate(err) for err in job.item_errors]
        response_data = JobResponse.model_validate(job).model_dump()
        return JobDetailResponse(**response_data, errors=error_items)

    async def list_jobs(
        self, user_id: uuid.UUID, filters: JobFilterParams
    ) -> PaginatedResponse[JobResponse]:
        items, total_count = await self.job_repo.filter_and_paginate(user_id, filters)
        job_responses = [JobResponse.model_validate(item) for item in items]
        return PaginatedResponse.create(
            items=job_responses,
            total_count=total_count,
            page=filters.page,
            page_size=filters.page_size,
        )

    async def retry_job(self, job_id: uuid.UUID, user_id: uuid.UUID) -> JobResponse:
        job = await self.job_repo.get_by_id(job_id, user_id)
        if not job:
            raise NotFoundError("Job", job_id)

        if job.status not in ("failed", "partially_failed"):
            raise BadRequestError(
                f"Cannot retry a job in '{job.status}' status. Only 'failed' or 'partially_failed' jobs can be retried."
            )
        if job.retry_count >= job.max_retries:
            raise BadRequestError(f"Job has exceeded maximum allowed retries ({job.max_retries}).")

        new_retry_count = job.retry_count + 1
        update_data = {
            "status": "queued",
            "retry_count": new_retry_count,
            "started_at": None,
            "completed_at": None,
            "error_summary": f"Job queued for retry (attempt {new_retry_count}/{job.max_retries})",
        }
        await self.job_repo.update_job(job_id, update_data)

        # Re-dispatch to worker
        dispatch_job(job_id)

        updated_job = await self.job_repo.get_by_id(job_id, user_id)
        return JobResponse.model_validate(updated_job)
