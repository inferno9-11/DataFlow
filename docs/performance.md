# DataFlow: Performance Benchmarks & Scalability Tuning

## 1. SQL Query Optimization Benchmark

To validate the indexing design, a reproducible benchmark was executed using `scripts/benchmark_queries.py`.

### Test Environment
- **Operating System**: Windows 11 (64-bit)
- **Runtime**: Python 3.13.1
- **Hardware**: 16 Logical CPU Cores, 15.65 GB RAM
- **Dataset Size**: 25,000 transaction records
- **Query Repetitions**: 100 iterations

### Target Query
```sql
SELECT * FROM records 
WHERE user_id = :uid 
ORDER BY occurred_at DESC 
LIMIT 50;
```

---

## 2. Empirical Benchmark Results

| Metric | Without Composite Index (`ix_records_user_id` only) | With Composite Index (`ix_records_user_occurred`) | Measured Performance Gain |
| :--- | :--- | :--- | :--- |
| **Mean Latency** | **8.09 ms** | **0.87 ms** | **9.3x faster** |
| **p50 (Median)** | **8.05 ms** | **0.84 ms** | **9.6x faster** |
| **p95 Latency** | **8.60 ms** | **1.16 ms** | **7.4x faster** |
| **p99 Latency** | **10.36 ms** | **1.29 ms** | **8.0x faster** |

### Execution Plan Analysis

#### 1. Baseline Plan (Without Composite Index):
```text
SEARCH records USING INDEX ix_records_user_id (user_id=?) -> USE TEMP B-TREE FOR ORDER BY
```
- **Bottleneck**: SQLite / PostgreSQL must locate all 25,000 rows for the tenant, copy them into an in-memory temporary B-Tree buffer, sort them by `occurred_at DESC`, and then return the top 50 records.

#### 2. Optimized Plan (With Composite Index):
```text
SEARCH records USING INDEX ix_records_user_occurred (user_id=?)
```
- **Optimization**: The composite index `(user_id, occurred_at DESC)` pre-sorts the leaf pointers. The database walks the index directly to `user_id` and reads the first 50 pointers sequentially. The temporary B-Tree sort is completely eliminated.

---

## 3. Database Connection Pool Configuration

In `app/core/config.py`, database pooling is configured with production-grade defaults:

```python
DB_POOL_SIZE = 20  # 20 steady-state persistent connections
DB_MAX_OVERFLOW = 10  # Up to 10 surge connections under heavy traffic spikes
DB_POOL_TIMEOUT = 30  # Max seconds a thread waits for an available connection
pool_pre_ping = True  # Tests socket connectivity before reusing pooled connections
```

---

## 4. Asynchronous Batch Chunking Tuning

When processing bulk batches up to 5,000 records:
1. Inserting 5,000 records in a single parameterized `INSERT` query exceeds SQL parameter limits (e.g., PostgreSQL has a 65,535 parameter ceiling; 5,000 records $\times$ 14 columns = 70,000 parameters).
2. The worker splits incoming records into controlled **chunks of 500 records** (`CHUNK_PROCESSING_SIZE = 500`).
3. Each chunk contains 7,000 parameters, well within relational database limits, maximizing throughput while minimizing transaction lock duration.

---

## 5. Running Locust Load Tests

To execute the load test scenario:

```bash
# 1. Start DataFlow locally
uvicorn app.main:app --port 8000 --workers 4

# 2. Run Locust in a separate terminal
locust -f tests/performance/locustfile.py --host http://localhost:8000
```
Open `http://localhost:8089` in your browser, configure 50 concurrent users with a spawn rate of 5 users/sec, and observe real-time throughput and latency percentiles.
