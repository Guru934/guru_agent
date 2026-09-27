from dataclasses import dataclass
from typing import Any, Dict, Callable
import datetime
import uuid

@dataclass
class AgentEvent:
    type: str # e.g. "TASK_STARTED", "TOOL_REQUESTED", "APPROVAL_REQUIRED", "TOOL_STARTED", "TOOL_FINISHED", "TASK_FAILED", "TASK_COMPLETED", "LOG"
    task_id: str
    payload: Dict[str, Any]
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.datetime.now().isoformat()

class EventBus:
    def __init__(self):
        self._subscribers = []

    def subscribe(self, callback: Callable[[AgentEvent], None]):
        self._subscribers.append(callback)

    def publish(self, event: AgentEvent):
        for sub in self._subscribers:
            try:
                sub(event)
            except Exception as e:
                print(f"Error in event subscriber: {e}")

# Global event bus
bus = EventBus()

def emit(type: str, task_id: str, payload: Dict[str, Any]):
    bus.publish(AgentEvent(type=type, task_id=task_id, payload=payload))
