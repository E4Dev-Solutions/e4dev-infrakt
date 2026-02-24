"""In-memory pub/sub for deployment log streaming."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field


@dataclass
class _DeploymentLog:
    """Holds log lines and subscribers for a single deployment."""

    lines: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    finished: bool = False
    subscribers: list[asyncio.Queue[str | None]] = field(default_factory=list)
    loop: asyncio.AbstractEventLoop | None = None


class LogBroadcaster:
    """Manages log streams for active deployments.

    The deploy background task (running in a thread) calls ``publish()`` and
    ``finish()``.  The async SSE endpoint calls ``subscribe()`` /
    ``unsubscribe()``.  Thread safety is achieved via ``threading.Lock`` on
    each deployment's state and ``call_soon_threadsafe`` to push items into
    asyncio queues from the worker thread.
    """

    def __init__(self) -> None:
        self._deployments: dict[int, _DeploymentLog] = {}
        self._global_lock = threading.Lock()

    def register(self, deployment_id: int, loop: asyncio.AbstractEventLoop) -> None:
        """Register a new deployment for streaming.

        Must be called *before* the background task starts.
        """
        with self._global_lock:
            self._deployments[deployment_id] = _DeploymentLog(loop=loop)

    def publish(self, deployment_id: int, line: str) -> None:
        """Publish a log line.  Thread-safe — called from background thread."""
        with self._global_lock:
            dep_log = self._deployments.get(deployment_id)
        if dep_log is None:
            return
        with dep_log.lock:
            dep_log.lines.append(line)
            for q in dep_log.subscribers:
                if dep_log.loop:
                    dep_log.loop.call_soon_threadsafe(q.put_nowait, line)

    def finish(self, deployment_id: int) -> None:
        """Signal that a deployment is complete.

        Sends a ``None`` sentinel to every subscriber queue.
        """
        with self._global_lock:
            dep_log = self._deployments.get(deployment_id)
        if dep_log is None:
            return
        with dep_log.lock:
            dep_log.finished = True
            for q in dep_log.subscribers:
                if dep_log.loop:
                    dep_log.loop.call_soon_threadsafe(q.put_nowait, None)

    def subscribe(self, deployment_id: int) -> tuple[list[str], asyncio.Queue[str | None]] | None:
        """Subscribe to a deployment's log stream.

        Returns ``(existing_lines, queue)`` or ``None`` if the deployment is
        not registered.  A ``None`` value read from the queue signals that the
        stream has ended.
        """
        with self._global_lock:
            dep_log = self._deployments.get(deployment_id)
        if dep_log is None:
            return None
        q: asyncio.Queue[str | None] = asyncio.Queue()
        with dep_log.lock:
            existing = list(dep_log.lines)
            if dep_log.finished:
                q.put_nowait(None)
            else:
                dep_log.subscribers.append(q)
        return existing, q

    def unsubscribe(self, deployment_id: int, q: asyncio.Queue[str | None]) -> None:
        """Remove a subscriber queue."""
        with self._global_lock:
            dep_log = self._deployments.get(deployment_id)
        if dep_log is None:
            return
        with dep_log.lock:
            try:
                dep_log.subscribers.remove(q)
            except ValueError:
                pass

    def has(self, deployment_id: int) -> bool:
        """Check if a deployment/key is currently registered."""
        with self._global_lock:
            return deployment_id in self._deployments

    def cleanup(self, deployment_id: int) -> None:
        """Remove all state for a deployment."""
        with self._global_lock:
            self._deployments.pop(deployment_id, None)


# Module-level singleton used by the API layer.
broadcaster = LogBroadcaster()
