import asyncio
import signal

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.session import async_session_factory
from app.models.job import ProcessingJob
from app.workers.job_processor import process_job

settings = get_settings()
setup_logging(level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)
logger = get_logger("dataflow.worker_runner")

_shutdown_requested = False


def handle_exit(sig, frame):
    global _shutdown_requested
    logger.info("Shutdown signal received. Exiting polling worker loop gracefully...")
    _shutdown_requested = True


async def run_standalone_poller():
    """
    Continuous worker loop polling database for queued jobs.
    Ensures background jobs are processed even in lightweight local setups
    where a separate Celery daemon is not active.
    """
    logger.info("Starting DataFlow standalone background job processor...")
    logger.info(
        f"Connected to database: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else 'local'}"
    )

    while not _shutdown_requested:
        try:
            job_to_process = None
            async with async_session_factory() as session:
                stmt = (
                    select(ProcessingJob.id)
                    .where(ProcessingJob.status == "queued")
                    .order_by(ProcessingJob.created_at.asc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                job_to_process = result.scalar_one_or_none()

            if job_to_process:
                logger.info(f"Picked up queued job {job_to_process} for processing.")
                await process_job(job_to_process)
            else:
                await asyncio.sleep(2.0)

        except Exception as e:
            logger.error(f"Error in worker polling loop: {e}")
            await asyncio.sleep(3.0)

    logger.info("Worker poller terminated.")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    asyncio.run(run_standalone_poller())
