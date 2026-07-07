from dataclasses import dataclass
from app.detection.category import DetectionCategory


@dataclass(frozen=True)
class RuleMetadata:
    name: str
    category: DetectionCategory
    description: str
