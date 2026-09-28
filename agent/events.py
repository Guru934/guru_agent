from dataclasses import dataclass
from typing import Any, Dict, Callable
import datetime
import uuid
import threading

@dataclass
class AgentEvent:
    type: str # e.g. "TASK_STARTED", "TOOL_REQUESTED", "APPROVAL_REQUIRED", "TOOL_STARTED", "TOOL_FINISHED", "TASK_BLOCKED", "TASK_FAILED", "TASK_COMPLETED", "LOG"
    task_id: str
    payload: Dict[str, Any]
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.datetime.now().isoformat()

class EventBus:
    def __init__(self):
        self._subscribers = []
        self._lock = threading.RLock()

    def subscribe(self, callback: Callable[[AgentEvent], None]):
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[AgentEvent], None]):
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def publish(self, event: AgentEvent):
        with self._lock:
            subscribers = tuple(self._subscribers)
        for sub in subscribers:
            try:
                sub(event)
            except Exception as e:
                print(f"Error in event subscriber: {e}")

# Global event bus
bus = EventBus()

def emit(type: str, task_id: str, payload: Dict[str, Any]):
    bus.publish(AgentEvent(type=type, task_id=task_id, payload=payload))
