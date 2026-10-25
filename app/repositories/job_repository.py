import uuid
from typing import Any

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.job import JobItemError, ProcessingJob
from app.repositories.base import BaseRepository
from app.schemas.job import JobFilterParams


class JobRepository(BaseRepository[ProcessingJob]):
    def __init__(self, session: AsyncSession):
        super().__init__(ProcessingJob, session)

    async def get_by_id(
        self, job_id: uuid.UUID, user_id: uuid.UUID, include_errors: bool = False
    ) -> ProcessingJob | None:
        stmt = select(ProcessingJob).where(
            ProcessingJob.id == job_id,
            ProcessingJob.user_id == user_id,
        )
        if include_errors:
            stmt = stmt.options(selectinload(ProcessingJob.item_errors))

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_system(
        self, job_id: uuid.UUID, include_errors: bool = False
    ) -> ProcessingJob | None:
        """System-level job retrieval for workers without tenant filtering."""
        stmt = select(ProcessingJob).where(ProcessingJob.id == job_id)
        if include_errors:
            stmt = stmt.options(selectinload(ProcessingJob.item_errors))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(
        self, idempotency_key: str, user_id: uuid.UUID
    ) -> ProcessingJob | None:
        stmt = select(ProcessingJob).where(
            ProcessingJob.idempotency_key == idempotency_key,
            ProcessingJob.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, job: ProcessingJob) -> ProcessingJob:
        self.session.add(job)
        await self.session.flush()
        return job

    async def update_job(self, job_id: uuid.UUID, update_data: dict[str, Any]) -> None:
        stmt = update(ProcessingJob).where(ProcessingJob.id == job_id).values(**update_data)
        await self.session.execute(stmt)
        await self.session.flush()

    async def filter_and_paginate(
        self, user_id: uuid.UUID, filters: JobFilterParams
    ) -> tuple[list[ProcessingJob], int]:
        conditions = [ProcessingJob.user_id == user_id]
        if filters.status:
            conditions.append(ProcessingJob.status == filters.status)
        if filters.job_type:
            conditions.append(ProcessingJob.job_type == filters.job_type)

        count_stmt = select(func.count(ProcessingJob.id)).where(*conditions)
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        offset = (filters.page - 1) * filters.page_size
        stmt = (
            select(ProcessingJob)
            .where(*conditions)
            .order_by(desc(ProcessingJob.created_at))
            .offset(offset)
            .limit(filters.page_size)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total_count

    async def add_item_errors(self, errors: list[JobItemError]) -> None:
        self.session.add_all(errors)
        await self.session.flush()

    async def get_job_errors(self, job_id: uuid.UUID, limit: int = 100) -> list[JobItemError]:
        stmt = (
            select(JobItemError)
            .where(JobItemError.job_id == job_id)
            .order_by(JobItemError.row_index)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
