import threading
import uuid
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from collections import deque

from agent.runtime import AgentRuntime
from agent.events import bus, emit, AgentEvent
from agent.approvals import manager as approval_manager
from agent.capabilities import registry as capability_registry
from agent.capabilities import CapabilityGrant
from agent.assistant_events import AssistantEvent


class TaskSummary:
    def __init__(self, task_id: str, description: str):
        self.task_id = task_id
        self.description = description
        self.status = "running"
        self.current_tool: Optional[str] = None
        self.progress_summary: str = ""
        self.approval_state: Optional[str] = None
        self.result_summary: Optional[str] = None
        self.error: Optional[str] = None
        self._cancellation_event = threading.Event()

    @property
    def cancellation_event(self) -> threading.Event:
        return self._cancellation_event


class ApprovalSummary:
    def __init__(self, approval_id: str, task_id: str, tool_name: str, arguments: Dict[str, Any], risk_level: str, reason: str):
        self.approval_id = approval_id
        self.task_id = task_id
        self.tool_name = tool_name
        self.arguments = arguments
        self.risk_level = risk_level
        self.reason = reason
        self.status = "pending"


class AssistantBridge:
    def __init__(self):
        self.active_tasks: Dict[str, TaskSummary] = {}
        self.pending_approvals: Dict[str, ApprovalSummary] = {}
        self.task_history: deque = deque(maxlen=20)  # Recent task history
        self._lock = threading.RLock()
        self._event_handlers: List[Callable[[AssistantEvent], None]] = []
        self._gemini_live_ref = None
        self._subscribed_to_bus = False
        self._session_start_time = datetime.now()
        
        self._subscribe_to_event_bus()

    def _subscribe_to_event_bus(self):
        if self._subscribed_to_bus:
            return
        bus.subscribe(self._on_agent_event)
        self._subscribed_to_bus = True

    def _on_agent_event(self, event: AgentEvent):
        task_id = event.task_id
        if event.type == "TASK_STARTED":
            desc = event.payload.get("description", "Unknown Task")
            with self._lock:
                if task_id not in self.active_tasks:
                    self.active_tasks[task_id] = TaskSummary(task_id, desc)
                self.active_tasks[task_id].status = "running"
            self._emit_assistant_event(AssistantEvent(
                type="task_started",
                task_id=task_id,
                summary=f"Started task: {desc}",
                risk=None,
            ))
            
        elif event.type == "TOOL_REQUESTED":
            tool_name = event.payload.get("tool_name", "")
            with self._lock:
                if task_id in self.active_tasks:
                    self.active_tasks[task_id].current_tool = tool_name
                    self.active_tasks[task_id].progress_summary = f"Running {tool_name}"
            self._emit_assistant_event(AssistantEvent(
                type="tool_progress",
                task_id=task_id,
                summary=f"Running {tool_name}",
                current_tool=tool_name,
                progress=f"Executing {tool_name}",
            ))
            
        elif event.type == "TOOL_FINISHED":
            tool_name = event.payload.get("tool_name", "")
            status = event.payload.get("status", "unknown")
            with self._lock:
                if task_id in self.active_tasks:
                    self.active_tasks[task_id].progress_summary = f"{tool_name} completed ({status})"
            self._emit_assistant_event(AssistantEvent(
                type="tool_progress",
                task_id=task_id,
                summary=f"{tool_name} completed",
                current_tool=tool_name,
                progress=f"Completed with status: {status}",
            ))
            
        elif event.type == "APPROVAL_REQUIRED":
            approval_id = event.payload.get("approval_id")
            tool_name = event.payload.get("tool_name", "")
            arguments = event.payload.get("arguments", {})
            risk_level = event.payload.get("risk_level", "medium")
            reason = event.payload.get("reason", "")
            
            with self._lock:
                if task_id in self.active_tasks:
                    self.active_tasks[task_id].approval_state = f"waiting ({tool_name})"
                if approval_id:
                    self.pending_approvals[approval_id] = ApprovalSummary(
                        approval_id, task_id, tool_name, arguments, risk_level, reason
                    )
            
            risk_map = {"low": "low", "medium": "medium", "high": "high", "critical": "critical"}
            risk_value: str = risk_map.get(risk_level, "medium")
            if risk_value not in ("low", "medium", "high", "critical"):
                risk_value = "medium"
            self._emit_assistant_event(AssistantEvent(
                type="approval_required",
                task_id=task_id,
                summary=f"Approval needed: {tool_name} - {reason}",
                risk=risk_value,  # type: ignore[arg-type]
                approval_id=approval_id,
                current_tool=tool_name,
            ))
            
        elif event.type in {"APPROVAL_GRANTED", "APPROVAL_REJECTED", "APPROVAL_TIMEOUT"}:
            approval_id = event.payload.get("approval_id")
            with self._lock:
                if approval_id and approval_id in self.pending_approvals:
                    self.pending_approvals[approval_id].status = event.type.lower()
                if task_id in self.active_tasks:
                    self.active_tasks[task_id].approval_state = None
                    
        elif event.type == "TASK_COMPLETED":
            result = event.payload.get("result", "")
            with self._lock:
                if task_id in self.active_tasks:
                    task = self.active_tasks[task_id]
                    task.status = "completed"
                    task.result_summary = result[:200] if result else ""
                    # Add to history
                    self.task_history.append({
                        "task_id": task_id,
                        "description": task.description,
                        "status": "completed",
                        "result_summary": task.result_summary,
                        "completed_at": datetime.now().isoformat(),
                    })
                    # Remove from active tasks
                    del self.active_tasks[task_id]
            self._emit_assistant_event(AssistantEvent(
                type="task_completed",
                task_id=task_id,
                summary=f"Task completed: {result[:150]}" if result else "Task completed",
                progress=result[:200] if result else None,
            ))

        elif event.type == "TASK_BLOCKED":
            reason = event.payload.get("reason", "Task is blocked.")
            with self._lock:
                if task_id in self.active_tasks:
                    task = self.active_tasks.pop(task_id)
                    task.status = "blocked"
                    task.error = reason
                    self.task_history.append({
                        "task_id": task_id,
                        "description": task.description,
                        "status": "blocked",
                        "error": reason,
                        "completed_at": datetime.now().isoformat(),
                    })
            self._emit_assistant_event(AssistantEvent(
                type="task_blocked",
                task_id=task_id,
                summary=f"Task blocked: {reason}",
                risk="high",
            ))
            
        elif event.type == "TASK_FAILED":
            error = event.payload.get("error", "Unknown error")
            with self._lock:
                if task_id in self.active_tasks:
                    task = self.active_tasks[task_id]
                    task.status = "failed"
                    task.error = error
                    # Add to history
                    self.task_history.append({
                        "task_id": task_id,
                        "description": task.description,
                        "status": "failed",
                        "error": error,
                        "completed_at": datetime.now().isoformat(),
                    })
                    # Remove from active tasks
                    del self.active_tasks[task_id]
            self._emit_assistant_event(AssistantEvent(
                type="task_failed",
                task_id=task_id,
                summary=f"Task failed: {error}",
                risk="critical",
            ))

    def _emit_assistant_event(self, event: AssistantEvent):
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                print(f"AssistantBridge event handler error: {e}")

    def register_event_handler(self, handler: Callable[[AssistantEvent], None]):
        self._event_handlers.append(handler)

    def set_gemini_live_ref(self, gemini_live_agent):
        self._gemini_live_ref = gemini_live_agent

    def delegate_task(self, description: str, model_id: Optional[str] = None, 
                        history: Optional[List[Dict[str, str]]] = None,
                        system_instruction: Optional[str] = None,
                        source: str = "gemini_live") -> str:
        task_id = str(uuid.uuid4())
        task_summary = TaskSummary(task_id, description)
        
        with self._lock:
            self.active_tasks[task_id] = task_summary
        
        def run_task():
            try:
                # Use the provided model_id (from Gemini Live) - AgentRuntime will
                # map live models to the configured heavy execution model via _execution_model_id()
                selected_model = model_id or "gemini-2.5-flash"
                runtime = AgentRuntime(model_id=selected_model)
                runtime.run(
                    request=description,
                    task_id=task_id,
                    cancellation_event=task_summary.cancellation_event,
                    history=history,
                    system_instruction=system_instruction,
                    enable_tools=True,
                )
            except Exception as e:
                emit("LOG", task_id, {"msg": f"Task execution error: {e}"})
        
        thread = threading.Thread(target=run_task, daemon=True)
        thread.start()
        
        return task_id

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self.active_tasks.get(task_id)
            if not task:
                return None
            return {
                "task_id": task.task_id,
                "description": task.description,
                "status": task.status,
                "current_tool": task.current_tool,
                "progress_summary": task.progress_summary,
                "approval_state": task.approval_state,
                "result_summary": task.result_summary,
                "error": task.error,
            }

    def get_active_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [status for tid in self.active_tasks.keys() if (status := self.get_task_status(tid)) is not None]

    def get_pending_approval(self, task_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            if task_id:
                for approval in self.pending_approvals.values():
                    if approval.task_id == task_id and approval.status == "pending":
                        return {
                            "approval_id": approval.approval_id,
                            "task_id": approval.task_id,
                            "tool_name": approval.tool_name,
                            "arguments": approval.arguments,
                            "risk_level": approval.risk_level,
                            "reason": approval.reason,
                        }
                return None
            else:
                for approval in self.pending_approvals.values():
                    if approval.status == "pending":
                        return {
                            "approval_id": approval.approval_id,
                            "task_id": approval.task_id,
                            "tool_name": approval.tool_name,
                            "arguments": approval.arguments,
                            "risk_level": approval.risk_level,
                            "reason": approval.reason,
                        }
                return None

    def get_all_pending_approvals(self) -> List[Dict[str, Any]]:
        """Get all pending approvals for disambiguation."""
        with self._lock:
            return [
                {
                    "approval_id": approval.approval_id,
                    "task_id": approval.task_id,
                    "tool_name": approval.tool_name,
                    "arguments": approval.arguments,
                    "risk_level": approval.risk_level,
                    "reason": approval.reason,
                }
                for approval in self.pending_approvals.values()
                if approval.status == "pending"
            ]

    def find_task_by_description(self, query: str) -> Optional[Dict[str, Any]]:
        """Find a task by fuzzy matching on description."""
        query_lower = query.lower()
        with self._lock:
            # First try exact match in active tasks
            for task in self.active_tasks.values():
                if query_lower in task.description.lower():
                    return self.get_task_status(task.task_id)
            
            # Then try recent history
            for hist in reversed(self.task_history):
                if query_lower in hist.get("description", "").lower():
                    return {
                        "task_id": hist["task_id"],
                        "description": hist["description"],
                        "status": hist["status"],
                        "result_summary": hist.get("result_summary", ""),
                        "error": hist.get("error", ""),
                        "completed_at": hist.get("completed_at", ""),
                    }
            return None

    def get_task_status_by_description(self, description: str) -> Optional[Dict[str, Any]]:
        """Get task status by description query (alias for find_task_by_description)."""
        return self.find_task_by_description(description)

    def approve_pending_action(self, approval_id: str) -> str:
        with self._lock:
            approval = self.pending_approvals.get(approval_id)
            if not approval:
                return f"Error: Approval {approval_id} not found."
            if approval.status != "pending":
                return f"Error: Approval {approval_id} already {approval.status}."
        
        try:
            approval_manager.approve(approval_id)
            with self._lock:
                if approval_id in self.pending_approvals:
                    self.pending_approvals[approval_id].status = "granted"
            return f"Approved: {approval.tool_name}"
        except ValueError as e:
            return f"Error: {e}"

    def reject_pending_action(self, approval_id: str) -> str:
        with self._lock:
            approval = self.pending_approvals.get(approval_id)
            if not approval:
                return f"Error: Approval {approval_id} not found."
            if approval.status != "pending":
                return f"Error: Approval {approval_id} already {approval.status}."
        
        try:
            approval_manager.reject(approval_id)
            with self._lock:
                if approval_id in self.pending_approvals:
                    self.pending_approvals[approval_id].status = "rejected"
            return f"Rejected: {approval.tool_name}"
        except ValueError as e:
            return f"Error: {e}"

    def get_capability_grants(self) -> List[Dict[str, Any]]:
        grants = capability_registry.get_all_grants()
        return [
            {
                "id": g.id,
                "capability": g.capability,
                "constraints": g.constraints,
                "scope": g.scope,
                "enabled": g.enabled,
                "created_at": g.created_at,
                "expires_at": g.expires_at,
            }
            for g in grants
        ]

    def revoke_capability_grant(self, grant_id: str) -> bool:
        return capability_registry.revoke_grant(grant_id)

    def get_current_state_summary(self) -> str:
        with self._lock:
            active = len(self.active_tasks)
            pending = len([a for a in self.pending_approvals.values() if a.status == "pending"])
            grants = capability_registry.get_all_grants()
            grant_list = ", ".join([g.capability for g in grants]) if grants else "None"
            
            lines = [
                "Current application: Guru Agent",
                "Current project: guru_agent",
                "Agent status: running" if active > 0 else "Agent status: idle",
                f"Active tasks: {active}",
                f"Pending approvals: {pending}",
                f"Trusted capabilities: {grant_list}",
            ]
            
            if active > 0:
                for task in self.active_tasks.values():
                    if task.status == "running":
                        lines.append(f"Active task: {task.description[:80]}")
                        if task.approval_state:
                            lines.append(f"Pending approval: {task.approval_state}")
                        break
            
            return "\n".join(lines)

    def get_session_context(self) -> str:
        """Get comprehensive session context for Gemini Live resumption."""
        with self._lock:
            active = len(self.active_tasks)
            pending = len([a for a in self.pending_approvals.values() if a.status == "pending"])
            grants = capability_registry.get_all_grants()
            grant_list = ", ".join([g.capability for g in grants]) if grants else "None"
            
            # Get project context
            project_context = self._get_project_context()
            
            # Get recent task history (last 5)
            recent_tasks = list(self.task_history)[-5:]
            history_lines = []
            for t in recent_tasks:
                status_icon = "✅" if t["status"] == "completed" else "❌"
                history_lines.append(f"  {status_icon} {t['description'][:60]} ({t['status']})")
            history_str = "\n".join(history_lines) if history_lines else "  (no recent tasks)"
            
            # Pending approvals detail
            pending_details = []
            for a in self.pending_approvals.values():
                if a.status == "pending":
                    pending_details.append(f"  - {a.tool_name}: {a.reason}")
            pending_str = "\n".join(pending_details) if pending_details else "  None"
            
            lines = [
                "=== SESSION CONTEXT ===",
                f"Session started: {self._session_start_time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"Current application: Guru Agent",
                f"Current project: guru_agent",
                project_context,
                f"Agent status: running" if active > 0 else "Agent status: idle",
                f"Active tasks: {active}",
                f"Pending approvals: {pending}",
                pending_str,
                f"Trusted capabilities: {grant_list}",
                f"Recent task history (last 5):",
                history_str,
            ]
            
            if active > 0:
                for task in self.active_tasks.values():
                    if task.status == "running":
                        lines.append(f"Active task: {task.description[:80]}")
                        if task.approval_state:
                            lines.append(f"Pending approval: {task.approval_state}")
                        break
            
            return "\n".join(lines)

    def get_project_context(self) -> str:
        """Get project/workspace context for the assistant."""
        return self._get_project_context()

    def _get_project_context(self) -> str:
        """Internal method to get project context."""
        import os
        try:
            # Get workspace root
            workspace = os.environ.get("WORKSPACE_ROOT", os.getcwd())
            project_name = os.path.basename(workspace)
            
            # Check for common project files
            project_files = []
            for fname in ["pyproject.toml", "package.json", "Cargo.toml", "go.mod", "requirements.txt", "README.md"]:
                if os.path.exists(os.path.join(workspace, fname)):
                    project_files.append(fname)
            
            # Get git status if available
            git_info = ""
            try:
                import subprocess
                result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], 
                                      capture_output=True, text=True, cwd=workspace, timeout=2)
                if result.returncode == 0:
                    branch = result.stdout.strip()
                    git_info = f"Git branch: {branch}"
            except Exception:
                pass
            
            lines = [f"Project: {project_name} ({workspace})"]
            if project_files:
                lines.append(f"Project files: {', '.join(project_files)}")
            if git_info:
                lines.append(git_info)
            
            return "\n".join(lines)
        except Exception:
            return "Project: guru_agent (workspace context unavailable)"

    def get_recent_task_history(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent task history for context."""
        with self._lock:
            return list(self.task_history)[-limit:]

    def get_context_for_resumption(self) -> Dict[str, Any]:
        """Get structured context for session resumption."""
        with self._lock:
            active_tasks = [
                {
                    "task_id": t.task_id,
                    "description": t.description,
                    "status": t.status,
                    "current_tool": t.current_tool,
                    "progress_summary": t.progress_summary,
                }
                for t in self.active_tasks.values()
            ]
            pending_approvals = [
                {
                    "approval_id": a.approval_id,
                    "task_id": a.task_id,
                    "tool_name": a.tool_name,
                    "arguments": a.arguments,
                    "risk_level": a.risk_level,
                    "reason": a.reason,
                }
                for a in self.pending_approvals.values() if a.status == "pending"
            ]
            recent_history = list(self.task_history)[-10:]
            
            return {
                "session_start_time": self._session_start_time.isoformat(),
                "active_tasks": active_tasks,
                "pending_approvals": pending_approvals,
                "recent_task_history": recent_history,
                "capability_grants": self.get_capability_grants(),
                "project_context": self._get_project_context(),
            }

    def compress_context(self, max_chars: int = 2000) -> str:
        """Compress context for long sessions - returns summarized context."""
        full_context = self.get_session_context()
        if len(full_context) <= max_chars:
            return full_context
        
        # Summarize: keep project, active tasks, pending approvals, truncate history
        lines = full_context.split("\n")
        essential = []
        history_started = False
        history_lines = []
        
        for line in lines:
            if "Recent task history" in line:
                history_started = True
                essential.append(line)
                continue
            if history_started:
                history_lines.append(line)
            else:
                essential.append(line)
        
        # Keep only last 3 history entries
        if len(history_lines) > 4:
            history_lines = history_lines[:1] + history_lines[-3:]
        
        compressed = "\n".join(essential + history_lines)
        if len(compressed) > max_chars:
            compressed = compressed[:max_chars] + "\n... (truncated)"
        
        return compressed

    def notify_agent_event(self, event: AssistantEvent):
        if self._gemini_live_ref and hasattr(self._gemini_live_ref, 'inject_agent_event'):
            self._gemini_live_ref.inject_agent_event(event)
