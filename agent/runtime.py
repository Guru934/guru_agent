import os
import threading
import uuid
from typing import Dict, List, Optional

from agent.events import emit
from agent.executor import ToolExecutor
from agent.model_provider import create_agent_session
from agent.state import TaskState
from agent.tool_registry import registry
from agent.fast_actions import resolve_fast_action


class AgentRuntime:
    def __init__(self, model_id: str = "gemini-2.5-flash"):
        self.model_id = model_id
        self.executor = ToolExecutor(registry)
        self._cancellation_tokens: Dict[str, threading.Event] = {}
        self._cancellation_lock = threading.Lock()

    def _execution_model_id(self) -> str:
        """Map realtime Live models to a normal text/tool model for execution."""
        if "live" in self.model_id.lower():
            return os.getenv("HEAVY_AGENT_MODEL", "gemini-3.1-flash-lite")
        return self.model_id

    def cancel_task(self, task_id: str) -> bool:
        with self._cancellation_lock:
            token = self._cancellation_tokens.get(task_id)
            if token is not None:
                token.set()
                return True
            return False

    def cancel_all(self):
        with self._cancellation_lock:
            for token in self._cancellation_tokens.values():
                token.set()

    def run(
        self,
        request: str,
        task_id: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        system_instruction: Optional[str] = None,
        cancellation_event: Optional[threading.Event] = None,
        enable_tools: bool = True,
    ) -> TaskState:
        task_id = task_id or str(uuid.uuid4())
        with self._cancellation_lock:
            if task_id in self._cancellation_tokens:
                raise ValueError(f"Task {task_id} is already running.")
            cancellation = cancellation_event or threading.Event()
            self._cancellation_tokens[task_id] = cancellation

        state = TaskState(task_id=task_id, original_request=request)
        emit("TASK_STARTED", task_id, {"description": request})
        default_instruction = (
            "You are a helpful local desktop assistant. "
            + (
                "Use registered tools for local operations. Tool arguments are validated and policy-checked. "
                if enable_tools
                else "No tools are available for this request; answer directly. "
            )
            + "Adapt to tool observations and provide a plain-text final answer when done."
        )
        system_instruction = "\n\n".join(
            part for part in (system_instruction, default_instruction) if part
        )
        conversation = list(history or [])
        session = None
        try:
            emit("LOG", task_id, {"msg": f"Starting agent runtime for prompt: {request}"})
            if cancellation.is_set():
                state.error = "Task cancelled by user."
                state.completed = True
                response = None
            else:
                fast_action = resolve_fast_action(request) if enable_tools else None
                if fast_action is not None:
                    emit(
                        "LOG",
                        task_id,
                        {"msg": f"Using deterministic fast path: {fast_action.tool_name}"},
                    )
                    result = self.executor.execute(
                        fast_action.tool_name,
                        fast_action.arguments,
                        {"task_id": task_id, "cancel_event": cancellation},
                    )
                    result_text = str(result.output)
                    state.add_observation(
                        fast_action.tool_name,
                        fast_action.arguments,
                        result_text,
                        is_error=result.status not in {"success"},
                    )
                    state.step_count = 1
                    if result.status == "success":
                        state.final_answer = result_text
                    else:
                        state.error = result_text
                    state.completed = True
                    response = None
                else:
                    session = create_agent_session(
                        self._execution_model_id(),
                        system_instruction,
                        registry.get_all_specs() if enable_tools else [],
                        conversation,
                    )
                    response = session.send_message(request)

            while not state.completed:
                if cancellation.is_set():
                    state.error = "Task cancelled by user."
                    state.completed = True
                    break

                if state.step_count >= state.max_steps:
                    state.error = f"Task exceeded maximum steps ({state.max_steps})."
                    state.completed = True
                    break

                if not response.function_calls:
                    state.final_answer = response.text
                    state.completed = True
                    break

                calls = response.function_calls
                results = []
                for call in calls:
                    result = self.executor.execute(
                        call.name,
                        call.arguments,
                        {"task_id": task_id, "cancel_event": cancellation},
                    )
                    result_text = str(result.output)
                    state.add_observation(
                        call.name,
                        call.arguments,
                        result_text,
                        is_error=result.status not in {"success"},
                    )
                    results.append(result_text)
                    emit(
                        "LOG",
                        task_id,
                        {"msg": f"Tool '{call.name}' resulted in: {result_text[:100]}..."},
                    )

                state.step_count += 1
                response = session.send_tool_results(calls, results)

        except Exception as error:
            state.error = f"Agent runtime failed: {error}"
            state.completed = True
        finally:
            # Close the agent session to release client resources
            if session is not None:
                try:
                    close = getattr(session, "close", None)
                    if close:
                        close()
                except Exception as close_error:
                    emit("LOG", task_id, {"msg": f"Agent session close error: {close_error}"})
            with self._cancellation_lock:
                self._cancellation_tokens.pop(task_id, None)

        if state.error:
            emit("TASK_FAILED", task_id, {"error": state.error})
        else:
            emit("TASK_COMPLETED", task_id, {"result": state.final_answer})
        return state
