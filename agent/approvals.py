import uuid
import threading
from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass, field

@dataclass
class PendingApproval:
    id: str
    tool_name: str
    arguments: Dict[str, Any]
    context: Dict[str, Any]
    risk_level: str
    reason: str
    on_approve: Callable[[], Any]
    on_reject: Callable[[], Any]

class ApprovalManager:
    def __init__(self):
        self._pending: Dict[str, PendingApproval] = {}
        self._lock = threading.Lock()

    def request_approval(self, 
                         tool_name: str, 
                         arguments: Dict[str, Any], 
                         context: Dict[str, Any], 
                         risk_level: str, 
                         reason: str,
                         on_approve: Callable[[], Any],
                         on_reject: Callable[[], Any]) -> str:
        approval_id = str(uuid.uuid4())
        approval = PendingApproval(
            id=approval_id,
            tool_name=tool_name,
            arguments=arguments,
            context=context,
            risk_level=risk_level,
            reason=reason,
            on_approve=on_approve,
            on_reject=on_reject
        )
        with self._lock:
            self._pending[approval_id] = approval
        
        # Publish an event that an approval is required
        from agent.events import emit
        task_id = context.get("task_id", "system")
        emit("APPROVAL_REQUIRED", task_id, {
            "approval_id": approval_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "risk_level": risk_level,
            "reason": reason
        })
        return approval_id

    def get_approval(self, approval_id: str) -> Optional[PendingApproval]:
        with self._lock:
            return self._pending.get(approval_id)

    def approve(self, approval_id: str) -> Any:
        with self._lock:
            approval = self._pending.pop(approval_id, None)
        if not approval:
            raise ValueError(f"Approval {approval_id} not found or already processed.")
        
        from agent.events import emit
        task_id = approval.context.get("task_id", "system")
        emit("APPROVAL_GRANTED", task_id, {"approval_id": approval_id})
        
        return approval.on_approve()

    def reject(self, approval_id: str) -> Any:
        with self._lock:
            approval = self._pending.pop(approval_id, None)
        if not approval:
            raise ValueError(f"Approval {approval_id} not found or already processed.")
        
        from agent.events import emit
        task_id = approval.context.get("task_id", "system")
        emit("APPROVAL_REJECTED", task_id, {"approval_id": approval_id})
        
        return approval.on_reject()

    def cancel(self, approval_id: str) -> bool:
        with self._lock:
            return self._pending.pop(approval_id, None) is not None

    def cancel_task(self, task_id: str) -> int:
        with self._lock:
            approval_ids = [
                approval_id
                for approval_id, approval in self._pending.items()
                if approval.context.get("task_id") == task_id
            ]
            for approval_id in approval_ids:
                self._pending.pop(approval_id, None)
            return len(approval_ids)

manager = ApprovalManager()
