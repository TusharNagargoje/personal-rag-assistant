import time
from typing import Dict, Tuple
from collections import defaultdict
from app.core.config import settings
from app.core.logging import logger

# In-memory sliding window fallback
_rate_limits: Dict[str, list] = defaultdict(list)


class RateLimiter:
    def __init__(self, requests_per_minute: int = 60):
        self.rpm = requests_per_minute

    async def is_rate_limited(self, identifier: str) -> Tuple[bool, int]:
        """
        Check if identifier has exceeded the allowed requests per minute.
        Returns (is_limited, retry_after_seconds).
        """
        now = time.time()
        window_start = now - 60.0

        # Optional Redis implementation if REDIS_URL configured
        if settings.REDIS_URL:
            try:
                import redis.asyncio as aioredis
                client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
                key = f"rate_limit:{identifier}"
                async with client.pipeline(transaction=True) as pipe:
                    pipe.zremrangebyscore(key, 0, window_start)
                    pipe.zadd(key, {str(now): now})
                    pipe.zcard(key)
                    pipe.expire(key, 65)
                    results = await pipe.execute()
                await client.aclose()
                request_count = results[2]
                if request_count > self.rpm:
                    return True, int(60 - (now - window_start))
                return False, 0
            except Exception as e:
                logger.debug(f"Redis rate limiter fallback to in-memory: {e}")

        # In-memory sliding window
        timestamps = _rate_limits[identifier]
        # Purge older than 60s
        _rate_limits[identifier] = [ts for ts in timestamps if ts > window_start]
        if len(_rate_limits[identifier]) >= self.rpm:
            return True, int(60 - (now - _rate_limits[identifier][0]))

        _rate_limits[identifier].append(now)
        return False, 0


rate_limiter = RateLimiter(requests_per_minute=120)
