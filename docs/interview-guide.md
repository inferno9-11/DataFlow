# DataFlow: Senior Backend Engineer Interview Guide & Technical Defenses

This document provides technically defensible answers to the most common architectural and behavioral questions asked in senior backend and systems engineering interviews, grounded directly in DataFlow's codebase.

---

## 1. Core Architectural Questions & Deep-Dive Answers

### Q1: Why was FastAPI chosen over Django or Flask?
**Answer**:
"FastAPI was selected for three primary reasons:
1. **Native Asynchronous Concurrency**: Built on Starlette and ASGI, FastAPI handles thousands of concurrent I/O-bound requests (e.g., waiting for PostgreSQL queries or Redis responses) on a single event loop without thread pool exhaustion.
2. **Compile-Time / Request-Time Schema Enforcement with Pydantic v2**: Pydantic v2's Rust core (`pydantic-core`) validates input payloads and serializes responses at speeds 5-15x faster than Python-only libraries like Marshmallow, while generating OpenAPI documentation automatically.
3. **Ergonomic Dependency Injection (`Depends`)**: FastAPI's DI system allows clean decoupling of route handlers from database sessions, services, and security context. This enables unit and integration testing with test database engines without monkeypatching."

---

### Q2: How does Authentication and Multi-Tenant Authorization work?
**Answer**:
"Authentication uses a stateless JWT model backed by **Argon2id** password hashing (`app/core/security.py`). Argon2id was selected over bcrypt and PBKDF2 because it is memory-hard (configured with 19 MiB memory cost and 2 iterations), which mitigates GPU and FPGA brute-force cracking.

For authorization:
1. When a client requests a protected endpoint, the `get_current_user` dependency decodes and verifies the JWT signature and expiration.
2. Tenant isolation is enforced inside the repository layer (`app/repositories/record_repository.py`). Every query incorporates `WHERE user_id = :uid`.
3. If an authenticated user attempts to access a resource ID owned by another user, the repository returns `None`, resulting in an HTTP `404 Not Found`. We purposefully return 404 rather than 403 to prevent object existence enumeration (IDOR protection)."

---

### Q3: How are Database Transactions and Connection Pooling handled?
**Answer**:
"Database access uses **SQLAlchemy 2.0** with explicit session lifecycles (`app/db/session.py`):
1. **Explicit Commit/Rollback**: The `get_db()` dependency uses an async context manager that automatically executes `await session.commit()` upon successful route execution. If any exception is raised, `await session.rollback()` is immediately invoked before the session is closed and returned to the pool.
2. **Connection Pooling**: In production with PostgreSQL, we use `QueuePool` configured with `pool_size=20`, `max_overflow=10`, `pool_timeout=30`, and `pool_pre_ping=True`. `pool_pre_ping` prevents 'server closed connection unexpectedly' errors by emitting a lightweight `SELECT 1` ping before handing a recycled connection to a request."

---

### Q4: Why is a Background Queue needed? Why not just use FastAPI `BackgroundTasks`?
**Answer**:
"FastAPI's built-in `BackgroundTasks` executes in-process on the same ASGI event loop or worker thread pool. This introduces severe production risks:
1. **Process Crash Loss**: If the API server crashes, restarts, or deploys while a background task is running, the in-memory task is permanently lost.
2. **Resource Starvation**: CPU-intensive parsing or large-batch ingestion starves the event loop, degrading API response times for all other users.
3. **No Distributed Concurrency or Retries**: `BackgroundTasks` cannot distribute work across multiple worker machines or manage exponential backoff retries.

By offloading to **Celery + Redis** (`app/workers/`):
- Jobs are persisted durably in PostgreSQL with a `queued` status and dispatched to Redis.
- Worker processes scale independently of API web servers.
- Automatic retry with exponential backoff (`backoff = base * 2^retry`) is supported."

---

### Q5: How do Idempotency and Deduplication work?
**Answer**:
"Idempotency guarantees that submitting the same request multiple times produces the exact same result without duplicate side-effects.

In DataFlow:
1. **Single Records**: A unique database constraint `uq_records_user_idempotency` on `(user_id, idempotency_key)` guarantees uniqueness per tenant. Before inserting, `record_repo.get_by_idempotency_key` checks for existing records; if found, the existing record is returned with `201 Created` without modifying state.
2. **Processing Jobs**: `processing_jobs` has a unique constraint `uq_jobs_user_idempotency` on `(user_id, idempotency_key)`. If a client resubmits a bulk job during a network timeout, the API returns the already-created `ProcessingJob` without enqueuing duplicate worker tasks.
3. **Intra-Batch Deduplication**: The worker maintains an in-memory hash set of seen `transaction_id` and `idempotency_key` values across the batch to catch duplicate items within the submitted payload."

---

### Q6: How is SQL Performance measured and optimized?
**Answer**:
"We optimized query latency from **8.09 ms down to 0.87 ms (9.3x faster)** on 25,000 records (`scripts/benchmark_queries.py`).

- **Query**: `SELECT * FROM records WHERE user_id = :uid ORDER BY occurred_at DESC LIMIT 50;`
- **Initial Plan**: `SEARCH records USING INDEX ix_records_user_id -> USE TEMP B-TREE FOR ORDER BY`. The database scanned matching tenant records and sorted them in a temporary in-memory B-Tree.
- **Optimization**: We created a composite index `ix_records_user_occurred ON records(user_id, occurred_at DESC)`.
- **New Plan**: `SEARCH records USING INDEX ix_records_user_occurred`. The database reads pre-sorted index pointers sequentially and stops after 50 rows, eliminating the temp B-Tree sort entirely."

---

### Q7: What happens when PostgreSQL, Redis, or a Worker fails?
**Answer**:
1. **PostgreSQL Fails**:
   - The readiness probe (`/health/ready`) immediately returns `503 Service Unavailable`.
   - Incoming requests trigger `AppException` error handlers and return standardized `500 INTERNAL_SERVER_ERROR` with a correlation `request_id`.
2. **Redis Fails**:
   - The readiness probe returns `degraded` (`200 OK` with dependency alert).
   - The rate limiter gracefully falls back to an in-memory sliding window.
   - Job submissions continue to persist `ProcessingJob` in PostgreSQL with status `queued`. `dispatch_job` catches the Redis connection failure, logs a warning, and prevents the HTTP request from crashing. When Redis restores or a standalone poller runs, the jobs are picked up.
3. **Worker Crashes Mid-Job**:
   - Celery is configured with `task_acks_late=True`. The broker does not acknowledge the message until the task finishes. If the worker terminates abruptly, the task is redelivered to an active worker.
   - For orphan jobs left in `running` state, the retry endpoint (`POST /api/v1/jobs/{id}/retry`) allows administrators or users to reset and re-dispatch eligible jobs."

---

### Q8: What does this architecture NOT guarantee?
**Answer**:
"Being candid about system boundaries is essential:
1. **Distributed Exactly-Once Delivery**: Like all distributed queue systems, Celery guarantees *at-least-once* task execution. If a worker inserts records and crashes immediately before updating `processing_jobs.status`, task redelivery could re-run the processor. DataFlow mitigates this via database idempotency constraints, but it is an *at-least-once execution with idempotent effects* model, not true magic exactly-once delivery.
2. **Cross-Region Active-Active Replication**: The database uses single-primary PostgreSQL. Read replicas can scale read traffic, but writes require routing to the primary."

---

### Q9: Which decisions would you change at 100x Scale (e.g., 50M records/day)?
**Answer**:
"If volume grew from thousands to millions of records per day:
1. **Partitioning**: Implement PostgreSQL declarative table partitioning by range on `occurred_at` (e.g., monthly partitions). Old partitions can be moved to cold storage or compressed.
2. **Event Streaming**: Replace Redis/Celery with Apache Kafka or AWS Kinesis to support partition-based consumer groups and replayable event logs.
3. **Read/Write Splitting**: Route analytical aggregate queries (`GET /analytics/summary`) to a read replica or OLAP data store (ClickHouse / Snowflake) to prevent locking primary OLTP tables."
