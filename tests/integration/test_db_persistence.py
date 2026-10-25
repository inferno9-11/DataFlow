from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.record import TransactionRecord
from app.models.user import User
from app.repositories.record_repository import RecordRepository
from app.repositories.user_repository import UserRepository
from app.schemas.record import RecordFilterParams


@pytest.mark.asyncio
async def test_user_creation_and_unique_constraint(db_session: AsyncSession):
    user_repo = UserRepository(db_session)
    user1 = User(
        email="unique@dataflow.dev",
        hashed_password="hashed_pw_1",
        full_name="User One",
        role="user",
        is_active=True,
    )
    await user_repo.create(user1)

    # Attempt to add duplicate email
    user2 = User(
        email="unique@dataflow.dev",
        hashed_password="hashed_pw_2",
        full_name="User Two",
        role="user",
        is_active=True,
    )
    with pytest.raises(IntegrityError):
        await user_repo.create(user2)
        await db_session.flush()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_record_persistence_and_bulk_insert(db_session: AsyncSession, test_user: User):
    record_repo = RecordRepository(db_session)

    records = [
        TransactionRecord(
            user_id=test_user.id,
            transaction_id=f"txn_{i}",
            account_id="acc_100",
            amount=Decimal(str(100.0 + i)),
            currency="USD",
            category="payment",
            merchant_name=f"Merchant {i}",
            status="cleared",
            risk_score=0.1,
            idempotency_key=f"idem_{i}",
        )
        for i in range(10)
    ]

    inserted = await record_repo.bulk_insert(records, chunk_size=5)
    assert len(inserted) == 10

    # Query with filters
    filters = RecordFilterParams(account_id="acc_100", page=1, page_size=5)
    items, total = await record_repo.filter_and_paginate(test_user.id, filters)
    assert total == 10
    assert len(items) == 5

    # Test analytics aggregation
    summary = await record_repo.get_analytics_summary(test_user.id)
    assert summary["total_records"] == 10
    assert summary["status_breakdown"]["cleared"] == 10
    assert summary["currency_breakdown"]["USD"] > 1000
