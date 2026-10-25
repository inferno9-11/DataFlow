import time
from collections import defaultdict

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.errors import RateLimitExceededError
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class InMemoryRateLimiter:
    """Sliding window rate limiter using in-memory timestamps per key."""

    def __init__(self):
        self._history: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        now = time.time()
        cutoff = now - window_seconds
        # Clean older entries
        self._history[key] = [t for t in self._history[key] if t > cutoff]

        if len(self._history[key]) >= max_requests:
            return False

        self._history[key].append(now)
        return True


class RateLimiter:
    """
    Production rate limiter with Redis backend and in-memory fallback.
    Prevents brute-force on authentication and throttling on bulk submission.
    """

    def __init__(self):
        self._in_memory = InMemoryRateLimiter()
        self._redis_client: aioredis.Redis | None = None

    async def get_redis(self) -> aioredis.Redis | None:
        if not settings.RATE_LIMIT_ENABLED:
            return None
        if self._redis_client is None:
            try:
                client = aioredis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=1.0,
                )
                await client.ping()
                self._redis_client = client
            except Exception as e:
                logger.warning(f"Redis unavailable for rate limiting, falling back to memory: {e}")
                self._redis_client = None
        return self._redis_client

    async def check_rate_limit(self, key: str, max_requests: int, window_seconds: int = 60) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return

        redis_client = await self.get_redis()
        if redis_client:
            try:
                current_time = int(time.time())
                redis_key = f"rate_limit:{key}:{current_time // window_seconds}"
                count = await redis_client.incr(redis_key)
                if count == 1:
                    await redis_client.expire(redis_key, window_seconds + 5)
                if count > max_requests:
                    raise RateLimitExceededError(
                        f"Rate limit exceeded: {max_requests} requests per {window_seconds}s allowed."
                    )
                return
            except RateLimitExceededError:
                raise
            except Exception as e:
                logger.warning(
                    f"Redis rate limit check failed ({e}), falling back to in-memory check"
                )

        # Fallback to in-memory limiter
        if not self._in_memory.check(key, max_requests, window_seconds):
            raise RateLimitExceededError(
                f"Rate limit exceeded: {max_requests} requests per {window_seconds}s allowed."
            )


limiter = RateLimiter()
