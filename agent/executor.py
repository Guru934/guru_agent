from typing import Dict, Any
from dataclasses import dataclass
import threading
import time

from agent.policy import engine as policy_engine
from agent.approvals import manager as approval_manager
from agent.events import emit
from agent.tool_registry import validate_arguments

@dataclass
class ExecutionResult:
    status: str
    output: Any


class ToolExecutor:
    def __init__(self, registry, approval_timeout: float = 300.0):
        if approval_timeout <= 0:
            raise ValueError("approval_timeout must be greater than zero.")
        self.registry = registry
        self.approval_timeout = approval_timeout

    @staticmethod
    def _finish(task_id: str, tool_name: str, result: ExecutionResult) -> ExecutionResult:
        emit(
            "TOOL_FINISHED",
            task_id,
            {"tool_name": tool_name, "status": result.status, "reason": str(result.output)},
        )
        return result

    def execute(self, tool_name: str, arguments: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        task_id = context.get("task_id", "system")
        emit("TOOL_REQUESTED", task_id, {"tool_name": tool_name, "arguments": arguments})

        spec = self.registry.get_spec(tool_name)
        if spec is None:
            return self._finish(task_id, tool_name, ExecutionResult("denied", f"Tool {tool_name} is not registered."))

        validation_error = validate_arguments(spec.input_schema, arguments)
        if validation_error:
            return self._finish(task_id, tool_name, ExecutionResult("invalid", validation_error))

        decision = policy_engine.evaluate(tool_name, arguments, context, tool_registry=self.registry)
        if not decision.allowed:
            return self._finish(
                task_id,
                tool_name,
                ExecutionResult("denied", f"Tool execution blocked by policy: {decision.reason}"),
            )

        if decision.requires_approval:
            approval_event = threading.Event()
            approval_response = {"status": None}

            def on_approve():
                approval_response["status"] = "approved"
                approval_event.set()
                return "Approved"

            def on_reject():
                approval_response["status"] = "denied"
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
            emit("LOG", task_id, {"msg": f"Waiting for approval (ID: {approval_id})..."})
            deadline = time.monotonic() + self.approval_timeout
            cancel_event = context.get("cancel_event")
            while not approval_event.is_set():
                if cancel_event is not None and cancel_event.is_set():
                    approval_manager.cancel(approval_id)
                    return self._finish(
                        task_id, tool_name,
                        ExecutionResult("cancelled", "Task cancelled while waiting for approval."),
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    approval_manager.cancel(approval_id)
                    emit("APPROVAL_TIMEOUT", task_id, {"approval_id": approval_id})
                    return self._finish(
                        task_id, tool_name, ExecutionResult("approval_timeout", "Approval request timed out.")
                    )
                approval_event.wait(min(0.1, remaining))

            if approval_response["status"] != "approved":
                return self._finish(
                    task_id, tool_name, ExecutionResult("denied", "User explicitly denied the operation.")
                )

        if context.get("cancel_event") is not None and context["cancel_event"].is_set():
            return self._finish(
                task_id, tool_name, ExecutionResult("cancelled", "Task cancelled before tool execution.")
            )
        return self._run_tool_logic(tool_name, arguments, task_id, context)

    def _run_tool_logic(
        self, tool_name: str, arguments: dict, task_id: str, context: Dict[str, Any] = None
    ) -> ExecutionResult:
        emit("TOOL_STARTED", task_id, {"tool_name": tool_name})
        try:
            func = self.registry.get_tool(tool_name)
            if not func:
                raise ValueError(f"Tool {tool_name} is not registered.")
                
            import inspect
            sig = inspect.signature(func)
            call_kwargs = dict(arguments)
            if "_task_id" in sig.parameters:
                call_kwargs["_task_id"] = task_id
            if "_workspace_dir" in sig.parameters and context:
                call_kwargs["_workspace_dir"] = context.get("workspace_dir")
                
            res = func(**call_kwargs)
            emit("TOOL_FINISHED", task_id, {"tool_name": tool_name, "status": "success", "output": str(res)[:500]})
            return ExecutionResult("success", res)
        except Exception as error:
            emit("TOOL_FINISHED", task_id, {"tool_name": tool_name, "status": "error", "error": str(error)})
            return ExecutionResult("error", str(error))
