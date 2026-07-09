from enum import Enum
from dataclasses import dataclass


class SecurityFramework(str, Enum):
    OWASP_LLM = "OWASP_LLM"
    MITRE_ATLAS = "MITRE_ATLAS"
    MITRE_ATTACK = "MITRE_ATTACK"


@dataclass(frozen=True)
class SecurityControlReference:
    framework: SecurityFramework
    control_id: str
    title: str
    version: str = "latest"
