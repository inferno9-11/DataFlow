import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import JobItemError, ProcessingJob
from app.models.user import User
from app.repositories.job_repository import JobRepository


@pytest.mark.asyncio
async def test_job_state_transitions_and_error_tracking(db_session: AsyncSession, test_user: User):
    job_repo = JobRepository(db_session)

    # 1. Create Queued Job
    job = ProcessingJob(
        user_id=test_user.id,
        job_type="bulk_transaction_ingest",
        status="queued",
        total_records=2,
        processed_records=0,
        failed_records=0,
    )
    saved = await job_repo.create(job)
    assert saved.status == "queued"
    assert saved.total_records == 2

    # 2. Add an item error
    err = JobItemError(
        job_id=saved.id,
        row_index=1,
        raw_data={"transaction_id": "bad_row"},
        error_code="VALIDATION_ERROR",
        error_message="Invalid currency",
    )
    await job_repo.add_item_errors([err])

    # 3. Transition to Partially Failed
    await job_repo.update_job(
        saved.id,
        {
            "status": "partially_failed",
            "processed_records": 1,
            "failed_records": 1,
            "error_summary": "1 succeeded, 1 failed",
        },
    )

    # 4. Fetch job with errors
    fetched = await job_repo.get_by_id(saved.id, test_user.id, include_errors=True)
    assert fetched is not None
    assert fetched.status == "partially_failed"
    assert len(fetched.item_errors) == 1
    assert fetched.item_errors[0].error_code == "VALIDATION_ERROR"
