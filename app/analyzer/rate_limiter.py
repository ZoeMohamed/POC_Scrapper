"""Token bucket async untuk membatasi request per menit."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable


class AsyncRateLimiter:
    def __init__(
        self,
        rpm: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rpm <= 0:
            raise ValueError("rpm harus lebih besar dari nol")
        self.capacity = float(rpm)
        self.tokens = float(rpm)
        self.refill_per_second = rpm / 60.0
        self._clock = clock
        self._updated_at = clock()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Tunggu hingga satu token tersedia lalu konsumsi token tersebut."""

        while True:
            async with self._lock:
                now = self._clock()
                elapsed = max(0.0, now - self._updated_at)
                self.tokens = min(
                    self.capacity, self.tokens + elapsed * self.refill_per_second
                )
                self._updated_at = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                delay = (1.0 - self.tokens) / self.refill_per_second
            await asyncio.sleep(delay)
