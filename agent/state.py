from dataclasses import dataclass, field
from typing import List, Literal

@dataclass
class OrchestrationPlan:
    route: Literal["direct", "desktop_action", "delegate"]
    preferred_model: str = "qwen2.5-coder"
    tool_calls: List[str] = field(default_factory=list)
    reason: str = ""
