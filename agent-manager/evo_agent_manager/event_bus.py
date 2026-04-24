"""In-process fan-out event bus for SSE streaming to dashboard clients."""

import asyncio
import json
import logging
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

MAX_HISTORY = 500


class EventBus:
    """Fan-out event bus: each SSE client gets its own asyncio.Queue."""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._history: dict[str, deque] = {}

    def publish(self, session_id: str, event: dict[str, Any]) -> None:
        """Push an event to all SSE subscribers for this session."""
        # Store in history
        if session_id not in self._history:
            self._history[session_id] = deque(maxlen=MAX_HISTORY)
        self._history[session_id].append(event)

        # Fan out to subscribers
        dead = []
        for i, q in enumerate(self._subscribers.get(session_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(i)
                logger.warning("SSE subscriber queue full, dropping")

        # Clean up full queues
        if dead:
            subscribers = self._subscribers[session_id]
            for i in reversed(dead):
                subscribers.pop(i)

    def subscribe(self, session_id: str) -> asyncio.Queue:
        """Create a subscription queue for a session. Returns the queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        if session_id not in self._subscribers:
            self._subscribers[session_id] = []
        self._subscribers[session_id].append(q)
        return q

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        """Remove a subscription queue."""
        if session_id in self._subscribers:
            try:
                self._subscribers[session_id].remove(queue)
            except ValueError:
                pass
            if not self._subscribers[session_id]:
                del self._subscribers[session_id]

    def get_recent_events(self, session_id: str, limit: int = 100) -> list[dict]:
        """Return recent events from history for replay."""
        history = self._history.get(session_id, deque())
        events = list(history)
        return events[-limit:]

    def subscriber_count(self, session_id: str) -> int:
        return len(self._subscribers.get(session_id, []))
