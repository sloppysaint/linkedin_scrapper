"""
rate_limiter.py — Simple async rate limiter to avoid hammering LinkedIn.

Enforces a minimum delay between outbound request batches so LinkedIn's
abuse detection is less likely to flag the account.
"""

import asyncio
import time


class RateLimiter:
    """
    Sliding-window rate limiter.

    Tracks when the last request batch was made and introduces a minimum
    delay before the next one. Thread-safe via asyncio.Lock.

    Args:
        min_delay_seconds: Minimum seconds to wait between consecutive
                           calls. Default 1.5s keeps activity human-paced.
    """

    def __init__(self, min_delay_seconds: float = 1.5) -> None:
        self._min_delay = min_delay_seconds
        self._last_call_at: float = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        """Await this before making outbound requests to LinkedIn."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call_at
            if elapsed < self._min_delay:
                await asyncio.sleep(self._min_delay - elapsed)
            self._last_call_at = time.monotonic()


# Singleton — shared across all requests so the delay is global
rate_limiter = RateLimiter()
