"""Tests for the in-memory deployment log broadcaster."""

from __future__ import annotations

import asyncio

from api.log_broadcaster import LogBroadcaster


class TestLogBroadcaster:
    """Core publish / subscribe / finish / cleanup behaviour."""

    def test_publish_stores_lines(self) -> None:
        b = LogBroadcaster()
        loop = asyncio.new_event_loop()
        b.register(1, loop)
        b.publish(1, "line-1")
        b.publish(1, "line-2")

        result = b.subscribe(1)
        assert result is not None
        existing, _ = result
        assert existing == ["line-1", "line-2"]
        loop.close()

    def test_subscribe_returns_none_for_unknown(self) -> None:
        b = LogBroadcaster()
        assert b.subscribe(999) is None

    def test_finish_sends_sentinel(self) -> None:
        b = LogBroadcaster()
        loop = asyncio.new_event_loop()
        b.register(1, loop)
        result = b.subscribe(1)
        assert result is not None
        _, queue = result

        async def _test() -> None:
            b.finish(1)
            await asyncio.sleep(0.01)
            item = queue.get_nowait()
            assert item is None  # sentinel

        loop.run_until_complete(_test())
        loop.close()

    def test_cleanup_removes_deployment(self) -> None:
        b = LogBroadcaster()
        loop = asyncio.new_event_loop()
        b.register(1, loop)
        b.publish(1, "hello")
        b.cleanup(1)
        assert b.subscribe(1) is None
        loop.close()

    def test_late_subscriber_gets_replay_plus_sentinel(self) -> None:
        """A subscriber joining after finish() gets existing lines + sentinel."""
        b = LogBroadcaster()
        loop = asyncio.new_event_loop()
        b.register(1, loop)
        b.publish(1, "a")
        b.publish(1, "b")
        b.finish(1)

        result = b.subscribe(1)
        assert result is not None
        existing, queue = result
        assert existing == ["a", "b"]
        assert queue.get_nowait() is None
        loop.close()

    def test_publish_to_unknown_is_noop(self) -> None:
        b = LogBroadcaster()
        # Should not raise
        b.publish(999, "ignored")

    def test_unsubscribe(self) -> None:
        b = LogBroadcaster()
        loop = asyncio.new_event_loop()
        b.register(1, loop)
        result = b.subscribe(1)
        assert result is not None
        _, queue = result
        b.unsubscribe(1, queue)
        # unsubscribing again should be a no-op
        b.unsubscribe(1, queue)
        loop.close()
