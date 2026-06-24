# Tool Model

## Objective

Define the metadata model used to govern enterprise tools.

---

## Motivation

Tools represent one of the primary attack surfaces within agentic systems.

To support authorization, risk assessment, detection, auditing, and future governance workflows, each tool must expose structured metadata.

---

## ToolMetadata

```python
ToolMetadata(
    tool_id: str,
    name: str,
    description: str,
    category: str,
    risk_level: str,
    required_permissions: list[str],
)
```

### Fields

| Field | Description |
|---------|-------------|
| tool_id | Unique identifier |
| name | Human-readable name |
| description | Tool purpose |
| category | Capability domain |
| risk_level | Tool risk classification |
| required_permissions | Required permissions |

---

## Categories

Initial categories:

- filesystem
- repository
- cloud
- network
- database

---

## Risk Levels

Supported risk levels:

- low
- medium
- high
- critical

---

## Example

```python
ToolMetadata(
    tool_id="file_read",
    name="File Read Tool",
    description="Read a file from the workspace",
    category="filesystem",
    risk_level="medium",
    required_permissions=["file.read"],
)
```

---

## Future Usage

Tool metadata will be consumed by:

- Authorization Service
- Risk Service
- Detection Service
- Approval Workflows (future)
- Management Console (future)
```