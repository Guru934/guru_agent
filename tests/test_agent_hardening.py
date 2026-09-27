import threading
import time
import unittest
import shlex
import subprocess
import sys
import tempfile
from unittest.mock import patch
from pathlib import Path

from agent.approvals import manager as approval_manager
from agent.executor import ToolExecutor
from agent.model_provider import AgentFunctionCall, AgentResponse, OllamaAgentSession, _gemini_schema
from agent.policy import engine as policy_engine
from agent.runtime import AgentRuntime
from agent.tool_registry import registry, validate_arguments
from config import APP_DIR
from tools.filesystem import read_file
from tools.shell import MAX_COMMAND_OUTPUT, execute_bash_command, _command_environment


class AgentHardeningTests(unittest.TestCase):
    def setUp(self):
        policy_engine.safe_mode = True
        audit_dir = tempfile.TemporaryDirectory()
        original_audit_file = policy_engine.audit_file
        policy_engine.audit_file = Path(audit_dir.name) / "security_audit.log"
        self.addCleanup(setattr, policy_engine, "audit_file", original_audit_file)
        self.addCleanup(audit_dir.cleanup)
        with approval_manager._lock:
            approval_manager._pending.clear()

    def test_tool_arguments_are_type_checked_and_closed(self):
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
            "additionalProperties": False,
        }
        self.assertIsNone(validate_arguments(schema, {"count": 2}))
        self.assertIn("must be integer", validate_arguments(schema, {"count": True}))
        self.assertIn("missing required", validate_arguments(schema, {}))
        self.assertIn("unsupported field", validate_arguments(schema, {"count": 2, "extra": 1}))

    def test_provider_schema_adapter_preserves_json_types(self):
        from google.genai import types

        schema = _gemini_schema({
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "enabled": {"type": "boolean"},
                "labels": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["count"],
        })
        self.assertEqual(schema.properties["count"].type, types.Type.INTEGER)
        self.assertEqual(schema.properties["enabled"].type, types.Type.BOOLEAN)
        self.assertEqual(schema.properties["labels"].items.type, types.Type.STRING)

    def test_ollama_adapter_sends_generic_schemas_and_tool_observations(self):
        first_response = unittest.mock.MagicMock()
        first_response.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "function": {
                        "name": "read_file",
                        "arguments": {"path": "README.md"},
                    }
                }],
            }
        }
        second_response = unittest.mock.MagicMock()
        second_response.json.return_value = {
            "message": {"role": "assistant", "content": "Done."}
        }
        session = OllamaAgentSession("test-model", "system prompt", registry.get_all_specs(), [])
        with patch("agent.model_provider.requests.post", side_effect=[first_response, second_response]) as post:
            tool_response = session.send_message("Read the README")
            final_response = session.send_tool_results(
                tool_response.function_calls,
                ["file content"],
            )

        self.assertEqual(tool_response.function_calls[0].arguments, {"path": "README.md"})
        self.assertEqual(final_response.text, "Done.")
        first_payload = post.call_args_list[0].kwargs["json"]
        self.assertEqual(first_payload["tools"][0]["function"]["parameters"]["type"], "object")
        tool_message = session.messages[-2]
        self.assertEqual(tool_message["role"], "tool")
        self.assertEqual(tool_message["tool_name"], "read_file")
        self.assertEqual(tool_message["content"], "file content")

    def test_executor_rejects_invalid_tool_arguments_before_handler(self):
        original_handler = registry.get_spec("write_file").handler
        writes = []
        registry.get_spec("write_file").handler = lambda **kwargs: writes.append(kwargs)
        try:
            result = ToolExecutor(registry).execute(
                "write_file",
                {"path": "valid.txt", "content": 123},
                {"task_id": "invalid-args"},
            )
        finally:
            registry.get_spec("write_file").handler = original_handler

        self.assertEqual(result.status, "invalid")
        self.assertEqual(writes, [])

    def test_shell_allowlist_does_not_accept_prefixes_or_outside_paths(self):
        safe = policy_engine.evaluate("execute_shell", {"command": "ls -la"}, {})
        chained = policy_engine.evaluate("execute_shell", {"command": "ls; rm -rf /"}, {})
        outside = policy_engine.evaluate("execute_shell", {"command": "cat ~/.ssh/id_rsa"}, {})
        destructive = policy_engine.evaluate("execute_shell", {"command": "rm -rf /"}, {})

        self.assertTrue(safe.allowed)
        self.assertFalse(safe.requires_approval)
        self.assertTrue(chained.requires_approval)
        self.assertTrue(outside.requires_approval)
        self.assertFalse(destructive.allowed)

    def test_safe_mode_off_matches_explicit_user_preference(self):
        policy_engine.safe_mode = False
        decision = policy_engine.evaluate("execute_shell", {"command": "npm install example"}, {})
        self.assertTrue(decision.allowed)
        self.assertFalse(decision.requires_approval)

    def test_filesystem_handler_enforces_workspace_even_when_called_directly(self):
        with self.assertRaises(PermissionError):
            read_file("/etc/passwd")

    def test_shell_has_bounded_output_and_fixed_execution_context(self):
        script = f"print('x' * {MAX_COMMAND_OUTPUT + 100})"
        command = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
        output = execute_bash_command(command)

        self.assertTrue(output.endswith("[Output truncated.]"))
        self.assertLessEqual(len(output), MAX_COMMAND_OUTPUT + len("\n[Output truncated.]"))
        self.assertEqual(execute_bash_command("pwd"), str(APP_DIR))
        self.assertNotIn("GEMINI_API_KEY", _command_environment())

    def test_shell_timeout_terminates_process_group(self):
        script = "import time; time.sleep(2)"
        command = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
        with patch("tools.shell.COMMAND_TIMEOUT_SECONDS", 0.02):
            with self.assertRaises(subprocess.TimeoutExpired):
                execute_bash_command(command)

    def test_policy_denies_execution_if_audit_cannot_be_written(self):
        with patch.object(policy_engine, "_log_audit", return_value=False):
            decision = policy_engine.evaluate("read_file", {"path": str(APP_DIR)}, {})
        self.assertFalse(decision.allowed)
        self.assertIn("audit could not be written", decision.reason)

    def test_approval_timeout_removes_pending_request(self):
        result = ToolExecutor(registry, approval_timeout=0.02).execute(
            "execute_shell",
            {"command": "npm install example"},
            {"task_id": "approval-timeout"},
        )

        self.assertEqual(result.status, "approval_timeout")
        self.assertEqual(approval_manager._pending, {})

    def test_cancellation_wakes_approval_wait(self):
        cancel_event = threading.Event()
        result_holder = []
        executor = ToolExecutor(registry, approval_timeout=5)
        thread = threading.Thread(
            target=lambda: result_holder.append(
                executor.execute(
                    "execute_shell",
                    {"command": "npm install example"},
                    {"task_id": "approval-cancel", "cancel_event": cancel_event},
                )
            )
        )
        thread.start()
        deadline = time.monotonic() + 1
        while not approval_manager._pending and time.monotonic() < deadline:
            time.sleep(0.005)
        cancel_event.set()
        thread.join(timeout=1)

        self.assertFalse(thread.is_alive())
        self.assertEqual(result_holder[0].status, "cancelled")
        self.assertEqual(approval_manager._pending, {})

    def test_approved_action_executes_on_waiting_worker_thread(self):
        tool = registry.get_spec("execute_shell")
        original_handler = tool.handler
        execution_threads = []
        tool.handler = lambda command: execution_threads.append(threading.get_ident()) or "done"
        worker_thread_id = []
        executor = ToolExecutor(registry)
        result_holder = []

        def run_tool():
            worker_thread_id.append(threading.get_ident())
            result_holder.append(
                executor.execute(
                    "execute_shell",
                    {"command": "npm install example"},
                    {"task_id": "approval-thread"},
                )
            )

        thread = threading.Thread(target=run_tool)
        try:
            thread.start()
            deadline = time.monotonic() + 1
            while not approval_manager._pending and time.monotonic() < deadline:
                time.sleep(0.005)
            approval_id = next(iter(approval_manager._pending))
            approval_manager.approve(approval_id)
            thread.join(timeout=1)
        finally:
            tool.handler = original_handler
            if thread.is_alive():
                thread.join(timeout=1)

        self.assertFalse(thread.is_alive())
        self.assertEqual(result_holder[0].status, "success")
        self.assertEqual(execution_threads, worker_thread_id)

    def test_runtime_checks_pre_cancel_before_provider_call_and_cleans_token(self):
        runtime = AgentRuntime(model_id="ollama-test")
        cancel_event = threading.Event()
        cancel_event.set()
        with patch("agent.runtime.create_agent_session") as create_session:
            state = runtime.run(
                "Stop",
                task_id="cancel-before-start",
                cancellation_event=cancel_event,
            )

        create_session.assert_not_called()
        self.assertEqual(state.error, "Task cancelled by user.")
        self.assertNotIn("cancel-before-start", runtime._cancellation_tokens)

    def test_runtime_uses_generic_provider_session_for_tool_cycle(self):
        session = unittest.mock.MagicMock()
        session.send_message.return_value = AgentResponse(
            text="",
            function_calls=[AgentFunctionCall(name="search", arguments={"query": "missing-token"})],
        )
        session.send_tool_results.return_value = AgentResponse(text="Done.", function_calls=[])
        with patch("agent.runtime.create_agent_session", return_value=session):
            state = AgentRuntime(model_id="ollama-test").run("Search the project")

        self.assertEqual(state.final_answer, "Done.")
        self.assertEqual(len(state.observations), 1)
        self.assertEqual(state.observations[0].tool_name, "search")
        session.send_tool_results.assert_called_once()


if __name__ == "__main__":
    unittest.main()
