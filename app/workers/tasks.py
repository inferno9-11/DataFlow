import asyncio
import uuid
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)
settings = get_settings()


@celery_app.task(name="tasks.process_bulk_job", bind=True, max_retries=3)
def process_bulk_job_task(self, job_id_str: str) -> dict[str, Any]:
    """
    Celery worker entrypoint for batch processing with automatic retry and exponential backoff.
    """
    from app.workers.job_processor import process_job

    job_id = uuid.UUID(job_id_str)
    logger.info(f"Celery task received for job {job_id} (attempt {self.request.retries + 1})")

    try:
        return asyncio.run(process_job(job_id))
    except Exception as exc:
        logger.error(f"Task execution failed for job {job_id}: {exc}")
        if self.request.retries < self.max_retries:
            backoff = settings.JOB_RETRY_BACKOFF_SECONDS * (2**self.request.retries)
            logger.warning(f"Retrying job {job_id} in {backoff} seconds...")
            raise self.retry(exc=exc, countdown=backoff) from exc
        raise exc


def dispatch_job(job_id: uuid.UUID) -> bool:
    """
    Safely dispatches job to Celery broker.
    In testing environment, avoids waiting for live broker.
    Fails fast with retry=False so HTTP requests never block when broker is unreachable.
    """
    if settings.ENVIRONMENT == "test":
        return True

    try:
        process_bulk_job_task.apply_async(
            args=[str(job_id)],
            retry=False,
            timeout=1.0,
        )
        logger.info(f"Successfully enqueued job {job_id} to Celery broker.")
        return True
    except Exception as e:
        logger.warning(
            f"Could not enqueue job {job_id} to Celery broker ({e}). "
            "Job remains persisted in database with status 'queued'."
        )
        return False
