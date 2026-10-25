import asyncio
import os
import platform
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import psutil
from sqlalchemy import Index, desc, select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.base import Base
from app.models.record import TransactionRecord
from app.models.user import User

BENCHMARK_DB = os.path.abspath("./benchmark_dataflow.db")
DATABASE_URL = f"sqlite+aiosqlite:///{BENCHMARK_DB}"
NUM_RECORDS = 25000
NUM_ITERATIONS = 100


async def run_benchmark():
    print("=" * 70)
    print(" DataFlow SQL Query Optimization & Indexing Benchmark")
    print("=" * 70)

    # 1. System Information
    cpu_count = psutil.cpu_count(logical=True)
    ram_gb = round(psutil.virtual_memory().total / (1024**3), 2)
    print(f"OS: {platform.system()} {platform.release()} ({platform.architecture()[0]})")
    print(f"Python: {platform.python_version()} | CPU Threads: {cpu_count} | RAM: {ram_gb} GB")
    print(f"Dataset Size: {NUM_RECORDS:,} records | Query Repetitions: {NUM_ITERATIONS}")
    print("-" * 70)

    # Clean existing benchmark database
    if os.path.exists(BENCHMARK_DB):
        os.remove(BENCHMARK_DB)

    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # 2. Insert synthetic records
    print(f"Generating and bulk inserting {NUM_RECORDS:,} records...")
    t0 = time.time()
    records = []
    for i in range(NUM_RECORDS):
        occurred = now - timedelta(minutes=i)
        records.append(
            TransactionRecord(
                user_id=user_id,
                transaction_id=f"txn_bench_{i:07d}",
                account_id=f"acc_{i % 50}",
                amount=Decimal(str(round(10.0 + (i % 5000), 2))),
                currency="USD",
                category="payment" if i % 2 == 0 else "transfer",
                merchant_name=f"Merchant {i % 100}",
                status="cleared" if i % 3 != 0 else "flagged",
                risk_score=0.1,
                occurred_at=occurred,
            )
        )

    async with session_factory() as session:
        for chunk_start in range(0, len(records), 1000):
            chunk = records[chunk_start : chunk_start + 1000]
            session.add_all(chunk)
            await session.flush()
        await session.commit()

    insert_time = time.time() - t0
    print(f"Bulk insert completed in {insert_time:.2f}s ({NUM_RECORDS / insert_time:.0f} rec/s)")
    print("-" * 70)

    # 3. Benchmark WITHOUT composite index
    # Temporarily drop index if created
    async with engine.begin() as conn:
        try:
            await conn.execute(text("DROP INDEX IF EXISTS ix_records_user_occurred"))
        except Exception:
            pass

    # Inspect query plan without index
    async with engine.connect() as conn:
        plan_no_idx = await conn.execute(
            text(
                "EXPLAIN QUERY PLAN "
                "SELECT * FROM records "
                "WHERE user_id = :uid "
                "ORDER BY occurred_at DESC LIMIT 50"
            ),
            {"uid": str(user_id)},
        )
        plan_text_no_idx = " -> ".join([f"{row[3]}" for row in plan_no_idx.fetchall()])

    print(f"Query Plan (Without Index):\n  {plan_text_no_idx}")

    # Measure latency WITHOUT index
    latencies_no_index = []
    async with session_factory() as session:
        for _ in range(NUM_ITERATIONS):
            start = time.perf_counter()
            stmt = (
                select(TransactionRecord)
                .where(TransactionRecord.user_id == user_id)
                .order_by(desc(TransactionRecord.occurred_at))
                .limit(50)
            )
            res = await session.execute(stmt)
            _ = res.scalars().all()
            latencies_no_index.append((time.perf_counter() - start) * 1000)

    # 4. Create Composite Index
    print("Creating composite index: ix_records_user_occurred ON records(user_id, occurred_at DESC)...")
    t_idx_start = time.time()
    async with engine.begin() as conn:
        await conn.execute(
            text("CREATE INDEX ix_records_user_occurred ON records(user_id, occurred_at DESC)")
        )
    idx_creation_time = time.time() - t_idx_start
    print(f"Index built in {idx_creation_time:.3f}s")

    # Inspect query plan WITH index
    async with engine.connect() as conn:
        plan_with_idx = await conn.execute(
            text(
                "EXPLAIN QUERY PLAN "
                "SELECT * FROM records "
                "WHERE user_id = :uid "
                "ORDER BY occurred_at DESC LIMIT 50"
            ),
            {"uid": str(user_id)},
        )
        plan_text_with_idx = " -> ".join([f"{row[3]}" for row in plan_with_idx.fetchall()])

    print(f"Query Plan (With Composite Index):\n  {plan_text_with_idx}")

    # Measure latency WITH index
    latencies_with_index = []
    async with session_factory() as session:
        for _ in range(NUM_ITERATIONS):
            start = time.perf_counter()
            stmt = (
                select(TransactionRecord)
                .where(TransactionRecord.user_id == user_id)
                .order_by(desc(TransactionRecord.occurred_at))
                .limit(50)
            )
            res = await session.execute(stmt)
            _ = res.scalars().all()
            latencies_with_index.append((time.perf_counter() - start) * 1000)

    # 5. Calculate Metrics
    latencies_no_index.sort()
    latencies_with_index.sort()

    def stats(l):
        p50 = l[int(len(l) * 0.50)]
        p95 = l[int(len(l) * 0.95)]
        p99 = l[int(len(l) * 0.99)]
        mean = sum(l) / len(l)
        return mean, p50, p95, p99

    no_mean, no_p50, no_p95, no_p99 = stats(latencies_no_index)
    with_mean, with_p50, with_p95, with_p99 = stats(latencies_with_index)

    speedup = no_mean / with_mean if with_mean > 0 else 1.0

    print("=" * 70)
    print(" BENCHMARK RESULTS SUMMARY (Latency in milliseconds)")
    print("=" * 70)
    print(f"{'Metric':<18} | {'No Index (Table Scan)':<22} | {'Composite Index':<20} | {'Improvement'}")
    print("-" * 70)
    print(f"{'Mean Latency':<18} | {no_mean:>18.2f} ms | {with_mean:>16.2f} ms | {speedup:.1f}x faster")
    print(f"{'p50 (Median)':<18} | {no_p50:>18.2f} ms | {with_p50:>16.2f} ms | {(no_p50/with_p50 if with_p50 > 0 else 1.0):.1f}x faster")
    print(f"{'p95 Latency':<18} | {no_p95:>18.2f} ms | {with_p95:>16.2f} ms | {(no_p95/with_p95 if with_p95 > 0 else 1.0):.1f}x faster")
    print(f"{'p99 Latency':<18} | {no_p99:>18.2f} ms | {with_p99:>16.2f} ms | {(no_p99/with_p99 if with_p99 > 0 else 1.0):.1f}x faster")
    print("=" * 70)

    await engine.dispose()
    if os.path.exists(BENCHMARK_DB):
        os.remove(BENCHMARK_DB)


if __name__ == "__main__":
    asyncio.run(run_benchmark())
