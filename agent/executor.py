from typing import Dict, Any, Union
from dataclasses import dataclass
from agent.policy import engine as policy_engine
from agent.approvals import manager as approval_manager
from agent.events import emit
import threading

@dataclass
class ExecutionResult:
    status: str # "success", "error", "denied"
    output: Any

class ToolExecutor:
    def __init__(self, registry):
        self.registry = registry

    def execute(self, tool_name: str, arguments: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        task_id = context.get("task_id", "system")
        emit("TOOL_REQUESTED", task_id, {"tool_name": tool_name, "arguments": arguments})

        # 1. Policy Evaluation
        decision = policy_engine.evaluate(tool_name, arguments, context)
        
        if not decision.allowed:
            emit("TOOL_FINISHED", task_id, {"tool_name": tool_name, "status": "denied", "reason": decision.reason})
            return ExecutionResult("denied", f"Tool execution blocked by policy: {decision.reason}")

        # 2. Synchronous Approval Flow
        if decision.requires_approval:
            approval_event = threading.Event()
            approval_response = {}
            
            def on_approve():
                res = self._run_tool_logic(tool_name, arguments, task_id)
                approval_response['status'] = res.status
                approval_response['output'] = res.output
                approval_event.set()
                return res.output
            
            def on_reject():
                approval_response['status'] = "denied"
                approval_response['output'] = "User explicitly denied the operation."
                approval_event.set()
                return "Denied"
                
            approval_id = approval_manager.request_approval(
                tool_name=tool_name,
                arguments=arguments,
                context=context,
                risk_level=decision.risk_level,
                reason=decision.reason,
                on_approve=on_approve,
                on_reject=on_reject
            )
            
            emit("LOG", task_id, {"msg": f"Blocking thread waiting for approval (ID: {approval_id})..."})
            approval_event.wait() # Pause background thread until UI resolves the dialog
            
            return ExecutionResult(approval_response['status'], approval_response['output'])

        # 3. Direct Execution
        return self._run_tool_logic(tool_name, arguments, task_id)

    def _run_tool_logic(self, tool_name: str, arguments: dict, task_id: str) -> ExecutionResult:
        emit("TOOL_STARTED", task_id, {"tool_name": tool_name})
        try:
            func = self.registry.get_tool(tool_name)
            if not func:
                raise ValueError(f"Tool {tool_name} is not registered.")
                
            res = func(**arguments)
            emit("TOOL_FINISHED", task_id, {"tool_name": tool_name, "status": "success", "output": str(res)[:500]})
            return ExecutionResult("success", res)
        except Exception as e:
            emit("TOOL_FINISHED", task_id, {"tool_name": tool_name, "status": "error", "error": str(e)})
            return ExecutionResult("error", str(e))
