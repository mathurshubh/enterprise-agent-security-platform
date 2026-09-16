"""Telemetry contracts according to ADR-015."""

from typing import Protocol

from app.models.telemetry.behavioral_event import BehavioralEvent


class TelemetryEmitter(Protocol):
    """Minimal, non-blocking interface for emitting telemetry events from the runtime security pipeline."""

    def emit(self, event: BehavioralEvent) -> None:
        """Emit an immutable telemetry event.

        Must provide non-blocking enqueue semantics and fail-silent isolation.
        Telemetry failures or buffer saturation must never raise an exception into the caller.
        """
        ...
