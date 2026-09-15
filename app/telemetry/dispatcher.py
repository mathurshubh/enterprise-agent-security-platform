"""In-memory telemetry dispatcher providing non-blocking asynchronous event buffering."""

import logging
import queue
import threading
from collections.abc import Callable
from typing import Final

from app.models.telemetry.behavioral_event import BehavioralEvent

logger = logging.getLogger(__name__)

DEFAULT_QUEUE_MAXSIZE: Final[int] = 10000


class InMemoryTelemetryDispatcher:
    """Non-blocking in-memory telemetry dispatcher according to ADR-015.

    Buffers emitted BehavioralEvent instances in a bounded queue and drains them
    asynchronously to registered subscribers via a background daemon thread.

    Provides best-effort asynchronous delivery and fail-silent error isolation.
    Queue saturation drops events rather than blocking the caller.
    """

    def __init__(
        self,
        max_queue_size: int = DEFAULT_QUEUE_MAXSIZE,
        start_worker: bool = True,
    ) -> None:
        self._max_queue_size = max_queue_size
        self._queue: queue.Queue[BehavioralEvent] = queue.Queue(maxsize=max_queue_size)
        self._subscribers: list[Callable[[BehavioralEvent], None]] = []
        self._lock = threading.RLock()
        self._dropped_events_count: int = 0
        self._running: bool = True

        self._worker_thread: threading.Thread | None = None
        if start_worker:
            self._start_worker()

    def _start_worker(self) -> None:
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="telemetry-dispatcher-worker",
        )
        self._worker_thread.start()

    @property
    def dropped_events_count(self) -> int:
        """Total number of events dropped due to buffer saturation or stopped state."""
        return self._dropped_events_count

    @property
    def queue_size(self) -> int:
        """Current number of pending events in the queue."""
        return self._queue.qsize()

    def subscribe(self, handler: Callable[[BehavioralEvent], None]) -> None:
        """Register a subscriber callback to receive dispatched events."""
        with self._lock:
            if handler not in self._subscribers:
                self._subscribers.append(handler)

    def unsubscribe(self, handler: Callable[[BehavioralEvent], None]) -> None:
        """Unregister a subscriber callback."""
        with self._lock:
            if handler in self._subscribers:
                self._subscribers.remove(handler)

    def emit(self, event: BehavioralEvent) -> None:
        """Emit an immutable telemetry event. Guaranteed non-blocking and fail-silent."""
        if not self._running:
            self._dropped_events_count += 1
            logger.warning("Telemetry event dropped: dispatcher is stopped.")
            return

        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self._dropped_events_count += 1
            logger.warning(
                "Telemetry event dropped: buffer saturated (capacity=%d).",
                self._max_queue_size,
            )
        except Exception as exc:  # pragma: no cover
            self._dropped_events_count += 1
            logger.warning("Telemetry emit error suppressed: %s", exc)

    def _worker_loop(self) -> None:
        """Background worker draining events and dispatching to subscribers."""
        while self._running or not self._queue.empty():
            try:
                event = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue

            try:
                with self._lock:
                    subscribers = list(self._subscribers)

                for subscriber in subscribers:
                    try:
                        subscriber(event)
                    except Exception as subscriber_exc:
                        logger.error(
                            "Subscriber error handling telemetry event %s: %s",
                            event.event_id,
                            subscriber_exc,
                            exc_info=True,
                        )
            finally:
                self._queue.task_done()

    def drain(self, timeout: float = 2.0) -> None:
        """Wait until all currently queued events have been processed by the worker."""
        try:
            # We wait up to timeout seconds for the queue to become empty and task_done called
            deadline = threading.Event()
            deadline.wait(0.01)  # small yield
            # Use queue.join with timeout approximation
            join_thread = threading.Thread(target=self._queue.join, daemon=True)
            join_thread.start()
            join_thread.join(timeout=timeout)
        except Exception:
            pass

    def close(self, timeout: float = 2.0) -> None:
        """Stop the dispatcher worker and drain pending events."""
        self._running = False
        self.drain(timeout=timeout)
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)
