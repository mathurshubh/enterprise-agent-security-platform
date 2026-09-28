"""Establishment of OS resource controls for sandboxed execution (ADR-032 §9.4).

A configured resource control is an execution precondition, not a best-effort
optimisation. The prior implementation attempted both limits inside one ``try`` and
swallowed every failure:

    try:
        setrlimit(RLIMIT_AS, ...)
        setrlimit(RLIMIT_CPU, ...)
    except (ImportError, ValueError, OSError):
        pass

That produced two defects. A failure left the control unestablished while the platform
continued as though it were enforced, and because memory was attempted first, its
failure meant the CPU limit was never attempted at all — one failure silently
suppressing an unrelated control.

Every control now receives an explicit outcome. There is no state in which a control is
neither established nor reported.
"""

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

MEMORY_CONTROL = "memory"
CPU_CONTROL = "cpu"

# A ceiling generous enough that any platform able to express a practical memory limit
# will accept it. Used only to tell "this mechanism cannot express a useful ceiling
# here" apart from "this particular configured value was rejected".
_GENEROUS_MEMORY_PROBE_BYTES = 64 * 1024 * 1024 * 1024


class ResourceControlOutcome(str, Enum):
    """The established state of one configured resource control."""

    ENFORCED = "ENFORCED"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ResourceControlAssessment:
    """What became of one control, and why."""

    control: str
    outcome: ResourceControlOutcome
    detail: str = ""

    @property
    def established(self) -> bool:
        return self.outcome is ResourceControlOutcome.ENFORCED


def _probe_source(max_memory_bytes: int, max_cpu_seconds: float) -> str:
    """Child program that reports what each control can actually establish.

    Runs in a throwaway process because establishing a limit is irreversible within a
    process: probing in the parent would narrow the platform's own limits.
    """
    cpu_seconds = int(max_cpu_seconds) + 1
    return f"""
import json, resource, sys

def attempt(rid, value):
    try:
        resource.setrlimit(rid, value)
        return None
    except Exception as exc:
        return f"{{type(exc).__name__}}: {{exc}}"

out = {{}}

mem_id = getattr(resource, "RLIMIT_AS", None)
if mem_id is None:
    out["{MEMORY_CONTROL}"] = ["UNSUPPORTED", "RLIMIT_AS is not available on this platform"]
else:
    err = attempt(mem_id, ({max_memory_bytes}, {max_memory_bytes}))
    if err is None:
        out["{MEMORY_CONTROL}"] = ["ENFORCED", ""]
    else:
        # Can the mechanism express any practical ceiling at all? If even a very
        # generous one is rejected, it cannot enforce a memory limit here; that is a
        # property of the platform rather than of the configured value.
        generous = attempt(mem_id, ({_GENEROUS_MEMORY_PROBE_BYTES}, {_GENEROUS_MEMORY_PROBE_BYTES}))
        if generous is None:
            out["{MEMORY_CONTROL}"] = ["FAILED", err]
        else:
            out["{MEMORY_CONTROL}"] = ["UNSUPPORTED", err]

cpu_id = getattr(resource, "RLIMIT_CPU", None)
if cpu_id is None:
    out["{CPU_CONTROL}"] = ["UNSUPPORTED", "RLIMIT_CPU is not available on this platform"]
else:
    err = attempt(cpu_id, ({cpu_seconds}, {cpu_seconds} + 1))
    out["{CPU_CONTROL}"] = ["ENFORCED", ""] if err is None else ["FAILED", err]

sys.stdout.write(json.dumps(out))
"""


_assessment_cache: dict[tuple[int, float], tuple[ResourceControlAssessment, ...]] = {}


def assess_resource_controls(
    max_memory_bytes: int,
    max_cpu_seconds: float,
) -> tuple[ResourceControlAssessment, ...]:
    """Determine what each configured control can establish on this platform.

    Cached per configured value: the answer depends on the platform and the requested
    ceiling, neither of which varies between executions of the same profile.
    """
    key = (max_memory_bytes, max_cpu_seconds)
    cached = _assessment_cache.get(key)
    if cached is not None:
        return cached

    if os.name != "posix":
        result = tuple(
            ResourceControlAssessment(
                control=control,
                outcome=ResourceControlOutcome.UNSUPPORTED,
                detail="POSIX resource limits are unavailable on this platform",
            )
            for control in (MEMORY_CONTROL, CPU_CONTROL)
        )
        _assessment_cache[key] = result
        return result

    try:
        completed = subprocess.run(
            [sys.executable, "-P", "-c", _probe_source(max_memory_bytes, max_cpu_seconds)],
            capture_output=True,
            timeout=30,
            check=False,
        )
        import json

        raw = json.loads(completed.stdout.decode("utf-8"))
    except Exception as exc:
        # The probe itself failing is not evidence that a control is enforceable, so it
        # is reported as a failure of every control rather than assumed benign.
        result = tuple(
            ResourceControlAssessment(
                control=control,
                outcome=ResourceControlOutcome.FAILED,
                detail=f"resource control probe failed: {type(exc).__name__}",
            )
            for control in (MEMORY_CONTROL, CPU_CONTROL)
        )
        _assessment_cache[key] = result
        return result

    result = tuple(
        ResourceControlAssessment(
            control=control,
            outcome=ResourceControlOutcome(raw[control][0]),
            detail=raw[control][1],
        )
        for control in (MEMORY_CONTROL, CPU_CONTROL)
    )
    _assessment_cache[key] = result
    return result


def apply_resource_controls(max_memory_bytes: int, max_cpu_seconds: float) -> None:
    """Establish the configured controls in the forked child, before exec.

    Each control is attempted independently, so one failure cannot prevent another from
    being established. Any failure raises, which aborts the launch: the workload never
    execs. Callers that have assessed a control as unenforceable must exclude it rather
    than relying on this to pass.
    """
    import resource

    failures: list[str] = []

    mem_id = getattr(resource, "RLIMIT_AS", None)
    if mem_id is not None and max_memory_bytes > 0:
        try:
            resource.setrlimit(mem_id, (max_memory_bytes, max_memory_bytes))
        except Exception as exc:
            failures.append(f"{MEMORY_CONTROL}: {type(exc).__name__}")

    cpu_id = getattr(resource, "RLIMIT_CPU", None)
    if cpu_id is not None and max_cpu_seconds > 0:
        cpu_seconds = int(max_cpu_seconds) + 1
        try:
            resource.setrlimit(cpu_id, (cpu_seconds, cpu_seconds + 1))
        except Exception as exc:
            failures.append(f"{CPU_CONTROL}: {type(exc).__name__}")

    if failures:
        raise RuntimeError(
            "sandbox resource controls could not be established: " + "; ".join(failures)
        )
