from enum import Enum


class ToolRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def severity(self) -> int:
        """Rank for ordering by risk, ascending.

        Declared explicitly because this is a ``str`` enum: the natural comparison is
        lexicographic, so ``max(LOW, HIGH, CRITICAL)`` is ``LOW``. Anything selecting the
        most restrictive level orders by this, never by the members themselves.
        """
        return _SEVERITY[self]


_SEVERITY: dict[ToolRiskLevel, int] = {
    ToolRiskLevel.LOW: 0,
    ToolRiskLevel.MEDIUM: 1,
    ToolRiskLevel.HIGH: 2,
    ToolRiskLevel.CRITICAL: 3,
}
