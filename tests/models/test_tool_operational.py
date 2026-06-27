from app.models.tool_operational import ToolOperational


def test_tool_operational_defaults() -> None:
    operational = ToolOperational()

    assert operational.enabled is True
    assert operational.timeout_seconds == 30
    assert operational.supports_streaming is False


def test_tool_operational_custom_values() -> None:
    operational = ToolOperational(
        enabled=False,
        timeout_seconds=120,
        supports_streaming=True,
    )

    assert operational.enabled is False
    assert operational.timeout_seconds == 120
    assert operational.supports_streaming is True