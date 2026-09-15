"""Unit tests for InMemoryTelemetryDispatcher according to ADR-015."""

import threading
import time

from app.models.telemetry.behavioral_event import BehavioralEvent
from app.models.telemetry.event_taxonomy import TelemetryEventType
from app.telemetry.dispatcher import InMemoryTelemetryDispatcher


def _create_sample_event(event_id: str = "evt-1") -> BehavioralEvent:
    return BehavioralEvent(
        event_id=event_id,
        event_type=TelemetryEventType.TOOL_INVOCATION_REQUESTED,
        session_id="sess-1",
        agent_id="agent-1",
    )


def test_dispatcher_emit_and_subscriber_delivery() -> None:
    dispatcher = InMemoryTelemetryDispatcher()
    received: list[BehavioralEvent] = []
    received_event = threading.Event()

    def handler(event: BehavioralEvent) -> None:
        received.append(event)
        received_event.set()

    try:
        dispatcher.subscribe(handler)
        sample = _create_sample_event()
        dispatcher.emit(sample)

        assert received_event.wait(timeout=2.0)
        assert len(received) == 1
        assert received[0].event_id == sample.event_id
    finally:
        dispatcher.close()


def test_dispatcher_multiple_subscribers() -> None:
    dispatcher = InMemoryTelemetryDispatcher()
    received_1: list[BehavioralEvent] = []
    received_2: list[BehavioralEvent] = []
    done_1 = threading.Event()
    done_2 = threading.Event()

    dispatcher.subscribe(lambda e: (received_1.append(e), done_1.set()))
    dispatcher.subscribe(lambda e: (received_2.append(e), done_2.set()))

    try:
        sample = _create_sample_event()
        dispatcher.emit(sample)

        assert done_1.wait(timeout=2.0)
        assert done_2.wait(timeout=2.0)
        assert len(received_1) == 1
        assert len(received_2) == 1
    finally:
        dispatcher.close()


def test_dispatcher_unsubscribe() -> None:
    dispatcher = InMemoryTelemetryDispatcher()
    received: list[BehavioralEvent] = []

    def handler(event: BehavioralEvent) -> None:
        received.append(event)

    dispatcher.subscribe(handler)
    dispatcher.unsubscribe(handler)

    try:
        dispatcher.emit(_create_sample_event())
        time.sleep(0.1)
        assert len(received) == 0
    finally:
        dispatcher.close()


def test_dispatcher_buffer_saturation_drops_events() -> None:
    # Worker is NOT started so queue fills up immediately
    dispatcher = InMemoryTelemetryDispatcher(max_queue_size=3, start_worker=False)

    try:
        # Fill the buffer
        for i in range(3):
            dispatcher.emit(_create_sample_event(f"evt-{i}"))
        assert dispatcher.dropped_events_count == 0
        assert dispatcher.queue_size == 3

        # 4th and 5th emits must drop without blocking or throwing exceptions
        dispatcher.emit(_create_sample_event("evt-overflow-1"))
        dispatcher.emit(_create_sample_event("evt-overflow-2"))

        assert dispatcher.dropped_events_count == 2
        assert dispatcher.queue_size == 3
    finally:
        dispatcher.close()


def test_dispatcher_fail_silent_subscriber_exception() -> None:
    dispatcher = InMemoryTelemetryDispatcher()
    successful_events: list[BehavioralEvent] = []
    done_event = threading.Event()

    def faulty_handler(event: BehavioralEvent) -> None:
        raise RuntimeError("Subscriber intentionally failed!")

    def working_handler(event: BehavioralEvent) -> None:
        successful_events.append(event)
        if len(successful_events) == 2:
            done_event.set()

    dispatcher.subscribe(faulty_handler)
    dispatcher.subscribe(working_handler)

    try:
        # Both emits must succeed without raising exception to caller
        dispatcher.emit(_create_sample_event("evt-1"))
        dispatcher.emit(_create_sample_event("evt-2"))

        assert done_event.wait(timeout=2.0)
        assert len(successful_events) == 2
    finally:
        dispatcher.close()


def test_dispatcher_stopped_drops_events() -> None:
    dispatcher = InMemoryTelemetryDispatcher()
    dispatcher.close()

    dispatcher.emit(_create_sample_event("evt-after-close"))
    assert dispatcher.dropped_events_count == 1
