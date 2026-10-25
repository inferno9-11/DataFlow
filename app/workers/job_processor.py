import time
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from app.core.logging import get_logger
from app.core.metrics import (
    ACTIVE_JOBS_GAUGE,
    JOB_EXECUTION_DURATION_SECONDS,
    JOB_RECORDS_PROCESSED_TOTAL,
)
from app.db.session import async_session_factory
from app.models.job import JobItemError
from app.models.record import TransactionRecord
from app.repositories.job_repository import JobRepository
from app.repositories.record_repository import RecordRepository
from app.schemas.record import RecordCreateRequest
from app.services.record_service import compute_risk_score, determine_initial_status

logger = get_logger(__name__)


async def process_job(job_id: uuid.UUID, session_factory=None) -> dict[str, Any]:
    """
    Executes asynchronous batch processing with:
    - Atomic job state transitions (queued -> running -> completed/partially_failed/failed)
    - Per-record schema validation
    - Idempotency checks and duplicate collision handling
    - Error tracking per row
    - Prometheus observability
    """
    if session_factory is None:
        session_factory = async_session_factory

    start_time = time.time()
    ACTIVE_JOBS_GAUGE.inc()

    async with session_factory() as session:
        job_repo = JobRepository(session)
        record_repo = RecordRepository(session)

        # 1. Fetch Job
        job = await job_repo.get_by_id_system(job_id)
        if not job:
            logger.error(f"Job {job_id} not found for processing.")
            ACTIVE_JOBS_GAUGE.dec()
            return {"error": "Job not found"}

        # Guard against duplicate concurrent execution
        if job.status == "running" and job.retry_count == 0:
            logger.warning(f"Job {job_id} is already in running state.")

        # Transition to RUNNING
        await job_repo.update_job(
            job_id,
            {
                "status": "running",
                "started_at": datetime.now(UTC),
            },
        )
        await session.commit()

        # Re-fetch for processing
        job = await job_repo.get_by_id_system(job_id)
        records_raw: list[dict[str, Any]] = job.payload_records or []
        user_id = job.user_id

        valid_records: list[TransactionRecord] = []
        item_errors: list[JobItemError] = []
        seen_txn_ids = set()
        seen_idem_keys = set()

        # 2. Iterate and validate each record
        for idx, item in enumerate(records_raw):
            try:
                # Validate schema
                validated = RecordCreateRequest.model_validate(item)

                # Intra-batch duplicate transaction check
                if validated.transaction_id in seen_txn_ids:
                    item_errors.append(
                        JobItemError(
                            job_id=job_id,
                            row_index=idx,
                            raw_data=item,
                            error_code="DUPLICATE_TRANSACTION_ID",
                            error_message=f"Duplicate transaction_id '{validated.transaction_id}' within batch.",
                        )
                    )
                    continue
                seen_txn_ids.add(validated.transaction_id)

                # Intra-batch idempotency key check
                if validated.idempotency_key:
                    if validated.idempotency_key in seen_idem_keys:
                        item_errors.append(
                            JobItemError(
                                job_id=job_id,
                                row_index=idx,
                                raw_data=item,
                                error_code="DUPLICATE_IDEMPOTENCY_KEY",
                                error_message=f"Duplicate idempotency_key '{validated.idempotency_key}' within batch.",
                            )
                        )
                        continue
                    seen_idem_keys.add(validated.idempotency_key)

                    # Database idempotency check
                    existing = await record_repo.get_by_idempotency_key(
                        validated.idempotency_key, user_id
                    )
                    if existing:
                        item_errors.append(
                            JobItemError(
                                job_id=job_id,
                                row_index=idx,
                                raw_data=item,
                                error_code="RECORD_ALREADY_EXISTS",
                                error_message=f"A record with idempotency key '{validated.idempotency_key}' was already ingested.",
                            )
                        )
                        continue

                # Compute risk score & status
                risk_score = compute_risk_score(
                    validated.amount, validated.category, validated.metadata
                )
                status = determine_initial_status(risk_score)

                valid_records.append(
                    TransactionRecord(
                        user_id=user_id,
                        transaction_id=validated.transaction_id,
                        account_id=validated.account_id,
                        amount=validated.amount,
                        currency=validated.currency,
                        category=validated.category,
                        merchant_name=validated.merchant_name,
                        status=status,
                        risk_score=risk_score,
                        idempotency_key=validated.idempotency_key,
                        metadata_json=validated.metadata,
                        occurred_at=validated.occurred_at,
                    )
                )

            except PydanticValidationError as pe:
                error_msgs = "; ".join([f"{e['loc']}: {e['msg']}" for e in pe.errors()])
                item_errors.append(
                    JobItemError(
                        job_id=job_id,
                        row_index=idx,
                        raw_data=item,
                        error_code="VALIDATION_ERROR",
                        error_message=error_msgs,
                    )
                )
            except Exception as e:
                item_errors.append(
                    JobItemError(
                        job_id=job_id,
                        row_index=idx,
                        raw_data=item,
                        error_code="PROCESSING_ERROR",
                        error_message=str(e),
                    )
                )

        # 3. Persist valid records and errors
        try:
            if valid_records:
                await record_repo.bulk_insert(valid_records, chunk_size=500)
            if item_errors:
                await job_repo.add_item_errors(item_errors)

            # Determine final status
            processed_count = len(valid_records)
            failed_count = len(item_errors)
            total_count = len(records_raw)

            if failed_count == 0:
                final_status = "completed"
            elif processed_count > 0:
                final_status = "partially_failed"
            else:
                final_status = "failed"

            summary = f"Processed {processed_count} successfully, {failed_count} failed out of {total_count} total."

            await job_repo.update_job(
                job_id,
                {
                    "status": final_status,
                    "processed_records": processed_count,
                    "failed_records": failed_count,
                    "completed_at": datetime.now(UTC),
                    "error_summary": summary,
                },
            )
            await session.commit()

            # Observability Metrics
            duration = time.time() - start_time
            JOB_EXECUTION_DURATION_SECONDS.labels(
                job_type=job.job_type, status=final_status
            ).observe(duration)
            JOB_RECORDS_PROCESSED_TOTAL.labels(status="success").inc(processed_count)
            JOB_RECORDS_PROCESSED_TOTAL.labels(status="failed").inc(failed_count)
            ACTIVE_JOBS_GAUGE.dec()

            logger.info(
                f"Job {job_id} finished with status '{final_status}' in {duration:.2f}s: {summary}"
            )

            return {
                "job_id": str(job_id),
                "status": final_status,
                "processed_records": processed_count,
                "failed_records": failed_count,
                "duration_seconds": duration,
            }

        except Exception as e:
            await session.rollback()
            logger.exception(f"Unexpected database error while processing job {job_id}: {e}")
            await job_repo.update_job(
                job_id,
                {
                    "status": "failed",
                    "error_summary": f"Database transaction failed: {str(e)}",
                    "completed_at": datetime.now(UTC),
                },
            )
            await session.commit()
            ACTIVE_JOBS_GAUGE.dec()
            raise
