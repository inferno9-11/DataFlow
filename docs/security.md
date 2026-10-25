# DataFlow: Security & Compliance Architecture

## 1. Authentication & Cryptography

### Argon2id Password Hashing
DataFlow uses **Argon2id** (the winner of the Password Hashing Competition, RFC 9106) rather than older SHA-based hashes or single-threaded bcrypt.

- **Algorithm**: Argon2id (hybrid memory-hard algorithm resisting both side-channel and GPU/ASIC cracking).
- **Parameters**:
  - `time_cost = 2`
  - `memory_cost = 19456 KiB` (19 MiB RAM per calculation)
  - `parallelism = 1`
  - `hash_len = 32 bytes`
  - `salt_len = 16 bytes` (cryptographically random per password)
- **Minimum Requirement**: Passwords must be at least 8 characters and are validated before hashing.

### JWT Access Tokens
- **Algorithm**: `HS256` signed using `SECRET_KEY` (minimum 256 bits of entropy in production).
- **Expiration**: Short-lived (30 minutes default).
- **Payload**: Contains subject (`sub`: user UUID), role (`role`), issue timestamp (`iat`), expiration (`exp`), and token type (`type: access`).
- **Validation**: Strict verification of signature, expiration, and required claims on every authenticated request.

---

## 2. Multi-Tenant Authorization & IDOR Defense

Insecure Direct Object References (IDOR) occur when an API accepts an object ID without validating that the authenticated user owns that object.

DataFlow prevents IDOR at the architectural level:
1. Route handlers extract the authenticated user identity via the `get_current_user` dependency.
2. The `user_id` is passed into all repository queries.
3. Every SQL query explicitly binds `WHERE user_id = :uid`:
   ```python
   stmt = select(TransactionRecord).where(
       TransactionRecord.id == record_id, TransactionRecord.user_id == current_user.id
   )
   ```
4. If a user queries a record ID belonging to another tenant, the repository returns `None`, and the API responds with `404 NOT_FOUND` (preventing information disclosure of object existence).

---

## 3. Rate Limiting Architecture

To protect authentication and bulk processing endpoints from denial-of-service and brute-force attacks:

| Endpoint | Window | Max Requests | Key Strategy | Action on Limit |
| :--- | :--- | :--- | :--- | :--- |
| `POST /api/v1/auth/login` | 60 seconds | 10 requests | Client IP | `429 Too Many Requests` |
| `POST /api/v1/records/bulk` | 60 seconds | 30 requests | `user_id` + Client IP | `429 Too Many Requests` |
| `POST /api/v1/jobs` | 60 seconds | 30 requests | `user_id` + Client IP | `429 Too Many Requests` |

### Resilient Fallback
The `RateLimiter` (`app/core/rate_limit.py`) attempts to connect to Redis. If Redis is unavailable or degraded, it automatically falls back to an in-memory sliding window limiter to prevent unhandled 500 errors.

---

## 4. Input Sanitization & SQL Injection Protection

- **Parameterized Statements**: DataFlow exclusively uses SQLAlchemy 2.0 object-relational mapping and bound parameters. Raw string concatenation is forbidden.
- **Allowlisted Sorting**: Client-supplied sorting parameters are strictly verified against an allowlist (`ALLOWED_SORT_FIELDS`). Any unrecognized column name causes immediate request rejection with `422 Unprocessable Entity`.
- **Bounded Payloads**:
  - Bulk synchronous ingestion is capped at `MAX_BULK_BATCH_SIZE = 5,000` records.
  - String fields have explicit `min_length` and `max_length` bounds to protect memory buffers.
