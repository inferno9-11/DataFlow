import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import async_engine, async_session_factory
from app.models.record import TransactionRecord
from app.models.user import User

CATEGORIES = ["payment", "transfer", "refund", "withdrawal", "deposit"]
STATUSES = ["cleared", "cleared", "cleared", "flagged", "pending"]
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CAD"]
MERCHANTS = [
    "AWS Cloud Services",
    "Stripe Payments",
    "GitHub Enterprise",
    "DigitalOcean",
    "Slack Technologies",
    "Uber Technologies",
    "Starbucks Coffee",
    "Apple Store",
]


async def seed():
    print("Initializing database tables...")
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        # Check if demo user already exists
        res = await session.execute(select(User).where(User.email == "demo@dataflow.dev"))
        demo_user = res.scalar_one_or_none()
        if demo_user:
            print("Demo user already exists.")
        else:
            print("Seeding demo and admin accounts...")
            demo_user = User(
                id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                email="demo@dataflow.dev",
                hashed_password=hash_password("DataFlow2026!Secure"),
                full_name="Demo Lead",
                role="user",
                is_active=True,
            )
            admin_user = User(
                id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                email="admin@dataflow.dev",
                hashed_password=hash_password("DataFlowAdmin2026!"),
                full_name="Security Admin",
                role="admin",
                is_active=True,
            )
            session.add_all([demo_user, admin_user])
            await session.commit()
        # Check if transaction records already exist for demo user
        res_rec = await session.execute(
            select(TransactionRecord).where(TransactionRecord.user_id == demo_user.id).limit(1)
        )
        if res_rec.scalar_one_or_none():
            print("Records for demo user already exist.")
            return

        print("Generating 1,000 synthetic transaction records for demo user...")
        records = []
        now = datetime.now(UTC)

        for i in range(1, 1001):
            occurred = now - timedelta(days=random.randint(0, 90), seconds=random.randint(0, 86400))
            amount = Decimal(str(round(random.uniform(5.0, 15000.0), 2)))
            category = random.choice(CATEGORIES)
            status = random.choice(STATUSES)
            risk = round(random.uniform(0.05, 0.85), 2)

            records.append(
                TransactionRecord(
                    user_id=demo_user.id,
                    transaction_id=f"txn_{occurred.strftime('%Y%m%d')}_{i:06d}",
                    account_id=f"acc_{random.randint(100, 105)}",
                    amount=amount,
                    currency=random.choice(CURRENCIES),
                    category=category,
                    merchant_name=random.choice(MERCHANTS),
                    status=status,
                    risk_score=risk,
                    metadata_json={"seed": True, "batch": 1},
                    occurred_at=occurred,
                )
            )

        session.add_all(records)
        await session.commit()
        print(f"Successfully seeded 2 users and {len(records)} transaction records!")


if __name__ == "__main__":
    asyncio.run(seed())
