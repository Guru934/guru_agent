from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class AssistantEvent:
    type: Literal["task_started", "approval_required", "task_completed", "task_failed", "tool_progress"]
    task_id: str
    summary: str
    risk: Literal["low", "medium", "high", "critical"] | None = None
    approval_id: Optional[str] = None
    current_tool: Optional[str] = None
    progress: Optional[str] = None