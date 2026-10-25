# DataFlow: Operational Runbooks & Troubleshooting Guide

This guide provides actionable runbooks for diagnosing and mitigating operational incidents in DataFlow.

---

## 1. Structured Log Analysis with `jq`

DataFlow emits single-line JSON logs containing correlation IDs (`request_id`).

### Extract errors across all services:
```bash
cat /var/log/dataflow.log | jq 'select(.level == "ERROR")'
```

### Trace all log entries for a specific request ID:
```bash
cat /var/log/dataflow.log | jq 'select(.request_id == "8b5fd681-3732-441f-8255-71ce8b99c855")'
```

### Filter by HTTP latency > 500ms:
```bash
cat /var/log/dataflow.log | jq 'select(.latency_seconds != null and .latency_seconds > 0.5)'
```

---

## 2. Diagnosing Slow Database Queries

If `GET /api/v1/records` latency exceeds acceptable thresholds:

1. Connect to PostgreSQL:
   ```bash
   docker exec -it dataflow_postgres psql -U postgres -d dataflow_db
   ```
2. Enable execution metrics and run `EXPLAIN (ANALYZE, BUFFERS)`:
   ```sql
   EXPLAIN (ANALYZE, BUFFERS)
   SELECT * FROM records 
   WHERE user_id = '11111111-1111-1111-1111-111111111111' 
   ORDER BY occurred_at DESC 
   LIMIT 50;
   ```
3. Check the plan:
   - **Good**: `Index Scan using ix_records_user_occurred`
   - **Bad**: `Seq Scan on records` or `Sort Method: external merge Disk`
4. If index is missing or corrupted:
   ```sql
   REINDEX INDEX CONCURRENTLY ix_records_user_occurred;
   ```

---

## 3. Investigating Stalled or Orphaned Processing Jobs

If jobs remain in `running` or `queued` state without updating:

### Step 1: Check Worker Container Status & Logs
```bash
docker compose logs worker --tail=100 -f
```

### Step 2: Inspect Redis Queue Backlog
```bash
docker exec -it dataflow_redis redis-cli
> LLEN celery
> KEYS *
```

### Step 3: Identify Orphaned Jobs in Database
```sql
SELECT id, user_id, status, started_at, retry_count 
FROM processing_jobs 
WHERE status = 'running' 
  AND started_at < NOW() - INTERVAL '15 minutes';
```

### Step 4: Reset and Retry Stalled Jobs via API
```bash
curl -X POST "http://localhost:8000/api/v1/jobs/<JOB_ID>/retry" \
  -H "Authorization: Bearer <ADMIN_OR_USER_TOKEN>"
```

---

## 4. Querying Prometheus Metrics

Scrape live operational metrics from the command line:

```bash
# Fetch all Prometheus metrics
curl -s http://localhost:8000/metrics

# Filter HTTP request counts
curl -s http://localhost:8000/metrics | grep dataflow_http_requests_total

# Inspect active background jobs
curl -s http://localhost:8000/metrics | grep dataflow_active_jobs

# Inspect job duration histogram buckets
curl -s http://localhost:8000/metrics | grep dataflow_job_execution_duration_seconds_bucket
```

---

## 5. Recovering from Alembic Migration Lock Contention

If `alembic upgrade head` hangs during deployment:

1. Check for active table locks in PostgreSQL:
   ```sql
   SELECT pid, query, state, age(clock_timestamp(), query_start) 
   FROM pg_stat_activity 
   WHERE state != 'idle' AND query ILIKE '%alembic%';
   ```
2. If a migration lock is held by a dead backend:
   ```sql
   SELECT pg_terminate_backend(pid);
   ```
3. Check the current migration version:
   ```sql
   SELECT * FROM alembic_version;
   ```
