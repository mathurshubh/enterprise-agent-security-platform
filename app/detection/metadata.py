from dataclasses import dataclass
from app.detection.category import DetectionCategory
from app.detection.security_standard import SecurityControlReference


@dataclass(frozen=True)
class RuleMetadata:
    name: str
    category: DetectionCategory
    description: str
    controls: tuple[SecurityControlReference, ...] = ()

