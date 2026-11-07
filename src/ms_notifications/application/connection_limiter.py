import asyncio


class RealtimeConnectionLimiter:
    def __init__(self, max_total: int, max_per_user: int) -> None:
        self._max_total = max_total
        self._max_per_user = max_per_user
        self._total = 0
        self._by_user: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, user_id: str) -> bool:
        async with self._lock:
            user_connections = self._by_user.get(user_id, 0)
            if self._total >= self._max_total or user_connections >= self._max_per_user:
                return False
            self._total += 1
            self._by_user[user_id] = user_connections + 1
            return True

    async def release(self, user_id: str) -> None:
        async with self._lock:
            user_connections = self._by_user.get(user_id, 0)
            if user_connections <= 0:
                return
            self._total -= 1
            if user_connections == 1:
                self._by_user.pop(user_id, None)
            else:
                self._by_user[user_id] = user_connections - 1

    async def counts(self, user_id: str) -> tuple[int, int]:
        async with self._lock:
            return self._total, self._by_user.get(user_id, 0)
