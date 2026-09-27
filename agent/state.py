from dataclasses import dataclass, field
from typing import List, Literal, Any, Dict, Optional
import datetime
import uuid

@dataclass
class OrchestrationPlan:
    route: Literal["direct", "desktop_action", "delegate"]
    preferred_model: str = "qwen2.5-coder"
    tool_calls: List[str] = field(default_factory=list)
    reason: str = ""

@dataclass
class Observation:
    step_number: int
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    is_error: bool = False
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().isoformat())

@dataclass
class TaskState:
    task_id: str
    original_request: str
    observations: List[Observation] = field(default_factory=list)
    completed: bool = False
    final_answer: str = ""
    error: Optional[str] = None
    step_count: int = 0
    max_steps: int = 15

    def add_observation(self, tool_name: str, arguments: Dict[str, Any], result: Any, is_error: bool = False):
        obs = Observation(
            step_number=self.step_count,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            is_error=is_error
        )
        self.observations.append(obs)
