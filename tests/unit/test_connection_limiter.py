import asyncio

from ms_notifications.application.connection_limiter import RealtimeConnectionLimiter


def test_connection_limits_and_release_are_enforced():
    async def scenario():
        limiter = RealtimeConnectionLimiter(max_total=2, max_per_user=1)

        assert await limiter.acquire("user-a") is True
        assert await limiter.acquire("user-a") is False
        assert await limiter.acquire("user-b") is True
        assert await limiter.acquire("user-c") is False
        assert await limiter.counts("user-a") == (2, 1)

        await limiter.release("user-a")
        assert await limiter.acquire("user-c") is True
        assert await limiter.counts("user-a") == (2, 0)

    asyncio.run(scenario())
