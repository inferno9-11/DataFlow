import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.record import TransactionRecord
from app.repositories.base import BaseRepository
from app.schemas.record import RecordFilterParams


class RecordRepository(BaseRepository[TransactionRecord]):
    def __init__(self, session: AsyncSession):
        super().__init__(TransactionRecord, session)

    async def get_by_id(self, record_id: uuid.UUID, user_id: uuid.UUID) -> TransactionRecord | None:
        """Fetches a single record ensuring strict multi-tenant isolation."""
        stmt = select(TransactionRecord).where(
            TransactionRecord.id == record_id,
            TransactionRecord.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(
        self, idempotency_key: str, user_id: uuid.UUID
    ) -> TransactionRecord | None:
        stmt = select(TransactionRecord).where(
            TransactionRecord.idempotency_key == idempotency_key,
            TransactionRecord.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, record: TransactionRecord) -> TransactionRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def bulk_insert(
        self, records: list[TransactionRecord], chunk_size: int = 500
    ) -> list[TransactionRecord]:
        """
        Inserts records in controlled batches to optimize throughput while avoiding
        parameter ceiling limits on relational databases.
        """
        for i in range(0, len(records), chunk_size):
            chunk = records[i : i + chunk_size]
            self.session.add_all(chunk)
            await self.session.flush()
        return records

    async def filter_and_paginate(
        self, user_id: uuid.UUID, filters: RecordFilterParams
    ) -> tuple[list[TransactionRecord], int]:
        """
        Dynamically applies allowlisted filters, sorting, and bounded pagination.
        Executes a separate COUNT query for accurate pagination metadata.
        """
        conditions = [TransactionRecord.user_id == user_id]

        if filters.account_id:
            conditions.append(TransactionRecord.account_id == filters.account_id)
        if filters.status:
            conditions.append(TransactionRecord.status == filters.status)
        if filters.category:
            conditions.append(TransactionRecord.category == filters.category)
        if filters.currency:
            conditions.append(TransactionRecord.currency == filters.currency.upper())
        if filters.min_amount is not None:
            conditions.append(TransactionRecord.amount >= filters.min_amount)
        if filters.max_amount is not None:
            conditions.append(TransactionRecord.amount <= filters.max_amount)
        if filters.start_date:
            conditions.append(TransactionRecord.occurred_at >= filters.start_date)
        if filters.end_date:
            conditions.append(TransactionRecord.occurred_at <= filters.end_date)

        # Count total matching rows
        count_stmt = select(func.count(TransactionRecord.id)).where(*conditions)
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        # Build main query with sorting
        stmt = select(TransactionRecord).where(*conditions)
        sort_column = getattr(TransactionRecord, filters.sort_by, TransactionRecord.occurred_at)
        if filters.sort_order == "desc":
            stmt = stmt.order_by(desc(sort_column))
        else:
            stmt = stmt.order_by(sort_column)

        offset = (filters.page - 1) * filters.page_size
        stmt = stmt.offset(offset).limit(filters.page_size)

        result = await self.session.execute(stmt)
        items = list(result.scalars().all())
        return items, total_count

    async def update(
        self, record_id: uuid.UUID, user_id: uuid.UUID, update_data: dict[str, Any]
    ) -> TransactionRecord | None:
        """Updates record attributes ensuring tenant isolation."""
        # Filter out None values
        clean_data = {k: v for k, v in update_data.items() if v is not None}
        if not clean_data:
            return await self.get_by_id(record_id, user_id)

        stmt = (
            update(TransactionRecord)
            .where(TransactionRecord.id == record_id, TransactionRecord.user_id == user_id)
            .values(**clean_data)
        )
        await self.session.execute(stmt)
        await self.session.flush()
        return await self.get_by_id(record_id, user_id)

    async def delete(self, record_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        stmt = delete(TransactionRecord).where(
            TransactionRecord.id == record_id,
            TransactionRecord.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def get_analytics_summary(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Calculates volume aggregations, status breakdowns, and average risk score."""
        base_where = TransactionRecord.user_id == user_id

        # 1. Total records, total amount, avg risk score
        agg_stmt = select(
            func.count(TransactionRecord.id).label("total_records"),
            func.coalesce(func.sum(TransactionRecord.amount), 0).label("total_amount"),
            func.coalesce(func.avg(TransactionRecord.risk_score), 0.0).label("avg_risk"),
        ).where(base_where)
        agg_res = (await self.session.execute(agg_stmt)).one()

        # 2. Status breakdown
        status_stmt = (
            select(
                TransactionRecord.status,
                func.count(TransactionRecord.id),
            )
            .where(base_where)
            .group_by(TransactionRecord.status)
        )
        status_res = (await self.session.execute(status_stmt)).all()
        status_breakdown = {row[0]: row[1] for row in status_res}

        # 3. Category breakdown
        cat_stmt = (
            select(
                TransactionRecord.category,
                func.count(TransactionRecord.id),
            )
            .where(base_where)
            .group_by(TransactionRecord.category)
        )
        cat_res = (await self.session.execute(cat_stmt)).all()
        category_breakdown = {row[0]: row[1] for row in cat_res}

        # 4. Currency breakdown
        curr_stmt = (
            select(
                TransactionRecord.currency,
                func.coalesce(func.sum(TransactionRecord.amount), Decimal(0)),
            )
            .where(base_where)
            .group_by(TransactionRecord.currency)
        )
        curr_res = (await self.session.execute(curr_stmt)).all()
        currency_breakdown = {row[0]: row[1] for row in curr_res}

        return {
            "total_records": agg_res.total_records,
            "total_amount": Decimal(str(agg_res.total_amount)),
            "average_risk_score": float(agg_res.avg_risk),
            "status_breakdown": status_breakdown,
            "category_breakdown": category_breakdown,
            "currency_breakdown": currency_breakdown,
        }
