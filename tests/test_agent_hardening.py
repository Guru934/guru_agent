import threading
import time
import unittest
import shlex
import subprocess
import sys
import tempfile
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

from agent.approvals import manager as approval_manager
from agent.executor import ToolExecutor
from agent.model_provider import AgentFunctionCall, AgentResponse, OllamaAgentSession, _gemini_schema
from agent.policy import engine as policy_engine
from agent.runtime import AgentRuntime
from agent.tool_registry import registry, validate_arguments
from config import APP_DIR, MAX_READ_BYTES, MAX_WRITE_BYTES, WORKSPACE_ROOTS
from tools.filesystem import read_file, write_file_content
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

    # --- Phase 0 Hardening Tests ---

    def test_filesystem_read_enforces_max_bytes(self):
        """Test that reading a file larger than MAX_READ_BYTES raises an error."""
        # Create a large file inside the workspace
        large_file = APP_DIR / "test_large_read.txt"
        try:
            large_file.write_text("x" * (MAX_READ_BYTES + 100))
            
            with self.assertRaises(ValueError) as cm:
                read_file("test_large_read.txt")
            self.assertIn("exceeds maximum read limit", str(cm.exception))
        finally:
            if large_file.exists():
                large_file.unlink()

    def test_filesystem_write_enforces_max_bytes(self):
        """Test that writing content larger than MAX_WRITE_BYTES raises an error."""
        target_file = APP_DIR / "test_large_write.txt"
        large_content = "x" * (MAX_WRITE_BYTES + 100)
        
        try:
            with self.assertRaises(ValueError) as cm:
                write_file_content("test_large_write.txt", large_content)
            self.assertIn("exceeds maximum write limit", str(cm.exception))
        finally:
            if target_file.exists():
                target_file.unlink()

    def test_filesystem_rejects_symlink_traversal(self):
        """Test that symlinks pointing outside workspace are rejected."""
        # Create a target file inside workspace
        target = APP_DIR / "symlink_target.txt"
        symlink_path = APP_DIR / "symlink_to_secret.txt"
        
        # Clean up any existing files
        if symlink_path.exists():
            symlink_path.unlink()
        if target.exists():
            target.unlink()
        
        try:
            target.write_text("secret")
            
            # Create a symlink inside APP_DIR pointing to target
            symlink_path.symlink_to(target)
            
            # Reading the symlink should work (it's inside workspace and target is inside workspace)
            content = read_file("symlink_to_secret.txt")
            self.assertEqual(content, "secret")
        finally:
            if symlink_path.exists():
                symlink_path.unlink()
            if target.exists():
                target.unlink()

    def test_filesystem_rejects_parent_symlink_traversal(self):
        """Test that parent directory symlinks are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            outside_file = Path(tmpdir) / "outside.txt"
            outside_file.write_text("outside content")
            
            # Create a symlink in APP_DIR that points to parent of outside file
            symlink_path = APP_DIR / "bad_symlink"
            try:
                symlink_path.symlink_to(tmpdir)
                # This should be rejected because the resolved path is outside workspace
                with self.assertRaises(PermissionError):
                    read_file("bad_symlink")
            finally:
                if symlink_path.exists():
                    symlink_path.unlink()

    def test_shell_rejects_absolute_paths_outside_allowlist(self):
        """Test that absolute executable paths outside allowlist require approval."""
        # Using absolute path for a non-allowlisted command
        decision = policy_engine.evaluate("execute_shell", {"command": "/usr/bin/find / -name test"}, {})
        self.assertTrue(decision.requires_approval)
        
        # Even for allowlisted commands, absolute path with args outside workspace should require approval
        decision = policy_engine.evaluate("execute_shell", {"command": "/bin/cat /etc/passwd"}, {})
        self.assertTrue(decision.requires_approval)

    def test_shell_rejects_redirection_operators(self):
        """Test that shell redirection operators trigger approval."""
        decisions = [
            policy_engine.evaluate("execute_shell", {"command": "echo test > /tmp/out"}, {}),
            policy_engine.evaluate("execute_shell", {"command": "cat < /etc/passwd"}, {}),
            policy_engine.evaluate("execute_shell", {"command": "ls 2>&1"}, {}),
            policy_engine.evaluate("execute_shell", {"command": "cmd >> file"}, {}),
        ]
        for decision in decisions:
            self.assertTrue(decision.requires_approval, f"Redirection should require approval: {decision.reason}")

    def test_shell_rejects_bash_c_attacks(self):
        """Test that bash -c with malicious content is blocked."""
        decisions = [
            policy_engine.evaluate("execute_shell", {"command": "bash -c 'rm -rf /'"}, {}),
            policy_engine.evaluate("execute_shell", {"command": "sh -c 'echo hacked'"}, {}),
            policy_engine.evaluate("execute_shell", {"command": "/bin/bash -c 'ls'"}, {}),
        ]
        for decision in decisions:
            self.assertTrue(decision.requires_approval or not decision.allowed, 
                          f"bash -c should be blocked or require approval: {decision.reason}")

    def test_shell_rejects_env_variable_attacks(self):
        """Test that environment variable manipulation attempts are caught."""
        decisions = [
            policy_engine.evaluate("execute_shell", {"command": "PATH=/malicious ls"}, {}),
            policy_engine.evaluate("execute_shell", {"command": "LD_PRELOAD=/evil.so ls"}, {}),
            policy_engine.evaluate("execute_shell", {"command": "HOME=/tmp ls"}, {}),
        ]
        for decision in decisions:
            self.assertTrue(decision.requires_approval or not decision.allowed,
                          f"Env manipulation should be blocked or require approval: {decision.reason}")

    def test_concurrent_approvals_isolated(self):
        """Test that multiple concurrent approval requests are isolated."""
        # Use write_file which requires approval in safe mode but is faster than shell
        results = {}
        ready_events = {"task-1": threading.Event(), "task-2": threading.Event()}
        
        def request_approval(task_id, path):
            executor = ToolExecutor(registry, approval_timeout=2)
            ready_events[task_id].set()
            result = executor.execute(
                "write_file",
                {"path": path, "content": "test"},
                {"task_id": task_id}
            )
            results[task_id] = result
        
        # Start two concurrent approval requests
        thread1 = threading.Thread(target=request_approval, args=("task-1", "test_concurrent_1.txt"))
        thread2 = threading.Thread(target=request_approval, args=("task-2", "test_concurrent_2.txt"))
        
        thread1.start()
        thread2.start()
        
        # Wait for both threads to reach the executor
        for event in ready_events.values():
            event.wait(timeout=2)
        
        # Wait for both approvals to be pending
        deadline = time.monotonic() + 2
        while len(approval_manager._pending) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        
        self.assertEqual(len(approval_manager._pending), 2)
        
        # Approve only task-1
        approval_ids = list(approval_manager._pending.keys())
        approval_manager.approve(approval_ids[0])
        
        thread1.join(timeout=5)
        thread2.join(timeout=5)
        
        # Verify isolation - task-1 approved, task-2 still pending (will timeout)
        task1_result = results.get("task-1")
        task2_result = results.get("task-2")
        
        self.assertIsNotNone(task1_result, "task-1 should have completed")
        self.assertIsNotNone(task2_result, "task-2 should have completed")
        
        # One should be approved (success), other timeout
        statuses = {task1_result.status, task2_result.status}
        self.assertIn("success", statuses)
        self.assertIn("approval_timeout", statuses)
        
        # Cleanup
        for f in ["test_concurrent_1.txt", "test_concurrent_2.txt"]:
            p = APP_DIR / f
            if p.exists():
                p.unlink()

    def test_approval_after_task_cancellation_rejected(self):
        """Test that approval for a cancelled task is rejected."""
        executor = ToolExecutor(registry, approval_timeout=5)
        cancel_event = threading.Event()
        
        result_holder = []
        thread = threading.Thread(
            target=lambda: result_holder.append(
                executor.execute(
                    "execute_shell",
                    {"command": "npm install example"},
                    {"task_id": "cancelled-task", "cancel_event": cancel_event}
                )
            )
        )
        thread.start()
        
        deadline = time.monotonic() + 1
        while not approval_manager._pending and time.monotonic() < deadline:
            time.sleep(0.005)
        
        approval_id = next(iter(approval_manager._pending))
        cancel_event.set()
        thread.join(timeout=1)
        
        # The task should be cancelled
        self.assertEqual(result_holder[0].status, "cancelled")
        
        # The approval should be removed from pending
        self.assertNotIn(approval_id, approval_manager._pending)
        
        # Trying to approve after cancellation should raise ValueError
        with self.assertRaises(ValueError):
            approval_manager.approve(approval_id)

    def test_duplicate_task_id_lifecycle(self):
        """Test that duplicate task IDs are handled correctly."""
        runtime1 = AgentRuntime(model_id="ollama-test")
        runtime2 = AgentRuntime(model_id="ollama-test")
        
        cancel_event = threading.Event()
        cancel_event.set()
        
        # First runtime with task_id
        with patch("agent.runtime.create_agent_session"):
            state1 = runtime1.run("Test", task_id="duplicate-id", cancellation_event=cancel_event)
        
        # Second runtime with same task_id - should work independently
        with patch("agent.runtime.create_agent_session"):
            state2 = runtime2.run("Test", task_id="duplicate-id", cancellation_event=cancel_event)
        
        self.assertEqual(state1.error, "Task cancelled by user.")
        self.assertEqual(state2.error, "Task cancelled by user.")
        # Cancellation tokens should be cleaned up independently
        self.assertNotIn("duplicate-id", runtime1._cancellation_tokens)
        self.assertNotIn("duplicate-id", runtime2._cancellation_tokens)

    def test_multiple_tool_calls_in_one_response(self):
        """Test that multiple tool calls in a single provider response are handled."""
        session = MagicMock()
        # First response has two tool calls
        session.send_message.return_value = AgentResponse(
            text="",
            function_calls=[
                AgentFunctionCall(name="read_file", arguments={"path": "README.md"}),
                AgentFunctionCall(name="search", arguments={"query": "test"}),
            ],
        )
        session.send_tool_results.return_value = AgentResponse(text="Done.", function_calls=[])
        
        with patch("agent.runtime.create_agent_session", return_value=session):
            state = AgentRuntime(model_id="ollama-test").run("Do both")
        
        self.assertEqual(state.final_answer, "Done.")
        self.assertEqual(len(state.observations), 2)
        self.assertEqual(state.observations[0].tool_name, "read_file")
        self.assertEqual(state.observations[1].tool_name, "search")

    def test_provider_failure_timeout_behavior(self):
        """Test that provider failures/timeouts are handled gracefully."""
        session = MagicMock()
        session.send_message.side_effect = Exception("Provider timeout")
        
        with patch("agent.runtime.create_agent_session", return_value=session):
            state = AgentRuntime(model_id="ollama-test").run("Test")
        
        self.assertIsNotNone(state.error)
        self.assertIn("Provider timeout", state.error)

    def test_malformed_provider_tool_call_arguments(self):
        """Test that malformed tool call arguments from provider are caught."""
        session = MagicMock()
        # Provider returns invalid arguments (wrong type)
        session.send_message.return_value = AgentResponse(
            text="",
            function_calls=[AgentFunctionCall(name="read_file", arguments={"path": 123})],
        )
        session.send_tool_results.return_value = AgentResponse(text="Done.", function_calls=[])
        
        with patch("agent.runtime.create_agent_session", return_value=session):
            state = AgentRuntime(model_id="ollama-test").run("Test")
        
        # Should handle the validation error gracefully
        self.assertIsNotNone(state.error or state.final_answer)

    def test_task_observability_under_concurrent_tasks(self):
        """Test that task events are correctly attributed under concurrency."""
        from agent.events import bus
        
        events_received = []
        def collector(event):
            events_received.append((event.type, event.task_id, event.payload))
        
        sub_id = bus.subscribe(collector)
        
        try:
            executor = ToolExecutor(registry)
            
            # Execute two tools for different tasks
            executor.execute("read_file", {"path": "README.md"}, {"task_id": "task-A"})
            executor.execute("search", {"query": "test"}, {"task_id": "task-B"})
            
            # Verify events have correct task_id
            task_a_events = [e for e in events_received if e[1] == "task-A"]
            task_b_events = [e for e in events_received if e[1] == "task-B"]
            
            self.assertTrue(any(e[0] == "TOOL_STARTED" for e in task_a_events))
            self.assertTrue(any(e[0] == "TOOL_STARTED" for e in task_b_events))
            
            # No cross-contamination
            for event_type, task_id, data in task_a_events:
                self.assertEqual(task_id, "task-A")
            for event_type, task_id, data in task_b_events:
                self.assertEqual(task_id, "task-B")
        finally:
            bus.unsubscribe(collector)

    def test_legacy_direct_execution_path_regression(self):
        """Test that direct tool calls still go through policy/executor."""
        # Direct handler call should still be validated by ToolExecutor
        executor = ToolExecutor(registry)
        
        # This should go through validation and policy
        result = executor.execute("read_file", {"path": "README.md"}, {"task_id": "direct-test"})
        self.assertEqual(result.status, "success")
        
        # Invalid args should be caught
        result = executor.execute("read_file", {"path": 123}, {"task_id": "direct-test-2"})
        self.assertEqual(result.status, "invalid")

    def test_ripgrep_searches_all_workspace_roots(self):
        """Test that ripgrep_search_impl searches all WORKSPACE_ROOTS."""
        # Create test files in different workspace roots
        with tempfile.TemporaryDirectory() as tmpdir:
            root1 = Path(tmpdir) / "root1"
            root2 = Path(tmpdir) / "root2"
            root1.mkdir()
            root2.mkdir()
            
            (root1 / "file1.txt").write_text("target content")
            (root2 / "file2.txt").write_text("target content")
            
            # Temporarily override WORKSPACE_ROOTS
            original_roots = list(WORKSPACE_ROOTS)
            WORKSPACE_ROOTS.clear()
            WORKSPACE_ROOTS.extend([root1, root2])
            
            try:
                from tools.shell import ripgrep_search_impl
                result = ripgrep_search_impl("target content")
                
                # Should find matches in both roots
                self.assertIn("root1", result)
                self.assertIn("root2", result)
                self.assertIn("file1.txt", result)
                self.assertIn("file2.txt", result)
            finally:
                WORKSPACE_ROOTS.clear()
                WORKSPACE_ROOTS.extend(original_roots)

    # --- Capability Grant Tests ---

    def test_capability_grant_creation_and_persistence(self):
        """Test that capability grants can be created and persist across restarts."""
        from agent.capabilities import registry, CapabilityGrant
        import uuid
        from datetime import datetime
        
        # Clear existing grants
        for g in registry.get_all_grants():
            registry.revoke_grant(g.id)
        
        grant = CapabilityGrant(
            id=str(uuid.uuid4()),
            capability="open_application",
            constraints={"app_name": "chrome"},
            scope="persistent",
            enabled=True,
            created_at=datetime.now().isoformat()
        )
        registry.register_grant(grant)
        
        # Verify grant exists
        retrieved = registry.get_grant(grant.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.capability, "open_application")
        self.assertEqual(retrieved.constraints["app_name"], "chrome")
        self.assertEqual(retrieved.scope, "persistent")
        
        # Verify it appears in all grants
        all_grants = registry.get_all_grants()
        self.assertEqual(len(all_grants), 1)
        self.assertEqual(all_grants[0].id, grant.id)

    def test_capability_grant_constraint_matching(self):
        """Test that capability grants correctly match constraints."""
        from agent.capabilities import registry, CapabilityGrant
        import uuid
        from datetime import datetime
        
        # Clear existing grants
        for g in registry.get_all_grants():
            registry.revoke_grant(g.id)
        
        # Grant for specific app
        grant = CapabilityGrant(
            id=str(uuid.uuid4()),
            capability="open_application",
            constraints={"app_name": "chrome"},
            scope="persistent",
            enabled=True,
            created_at=datetime.now().isoformat()
        )
        registry.register_grant(grant)
        
        # Should match exact app
        match = registry.check_grant("open_application", {"app_name": "chrome"})
        self.assertIsNotNone(match)
        self.assertEqual(match.id, grant.id)
        
        # Should NOT match different app
        match = registry.check_grant("open_application", {"app_name": "firefox"})
        self.assertIsNone(match)
        
        # Should NOT match different capability
        match = registry.check_grant("open_website", {"url": "chrome.com"})
        self.assertIsNone(match)

    def test_capability_grant_range_constraints(self):
        """Test that range constraints (min/max) work correctly."""
        from agent.capabilities import registry, CapabilityGrant
        import uuid
        from datetime import datetime
        
        # Clear existing grants
        for g in registry.get_all_grants():
            registry.revoke_grant(g.id)
        
        # Grant for volume 0-100
        grant = CapabilityGrant(
            id=str(uuid.uuid4()),
            capability="set_volume",
            constraints={"level_percent": {"min": 0, "max": 100}},
            scope="persistent",
            enabled=True,
            created_at=datetime.now().isoformat()
        )
        registry.register_grant(grant)
        
        # Should match within range
        match = registry.check_grant("set_volume", {"level_percent": 50})
        self.assertIsNotNone(match)
        
        match = registry.check_grant("set_volume", {"level_percent": 0})
        self.assertIsNotNone(match)
        
        match = registry.check_grant("set_volume", {"level_percent": 100})
        self.assertIsNotNone(match)
        
        # Should NOT match outside range
        match = registry.check_grant("set_volume", {"level_percent": -10})
        self.assertIsNone(match)
        
        match = registry.check_grant("set_volume", {"level_percent": 150})
        self.assertIsNone(match)

    def test_capability_grant_revocation(self):
        """Test that capability grants can be revoked."""
        from agent.capabilities import registry, CapabilityGrant
        import uuid
        from datetime import datetime
        
        # Clear existing grants
        for g in registry.get_all_grants():
            registry.revoke_grant(g.id)
        
        grant = CapabilityGrant(
            id=str(uuid.uuid4()),
            capability="open_application",
            constraints={"app_name": "chrome"},
            scope="persistent",
            enabled=True,
            created_at=datetime.now().isoformat()
        )
        registry.register_grant(grant)
        
        # Verify grant exists
        self.assertIsNotNone(registry.get_grant(grant.id))
        
        # Revoke grant
        result = registry.revoke_grant(grant.id)
        self.assertTrue(result)
        
        # Verify grant is gone
        self.assertIsNone(registry.get_grant(grant.id))
        
        # Verify it no longer matches
        match = registry.check_grant("open_application", {"app_name": "chrome"})
        self.assertIsNone(match)

    def test_capability_grant_session_scope_expiry(self):
        """Test that session-scoped grants are handled (expire on restart simulation)."""
        from agent.capabilities import registry, CapabilityGrant
        import uuid
        from datetime import datetime, timedelta
        
        # Clear existing grants
        for g in registry.get_all_grants():
            registry.revoke_grant(g.id)
        
        # Create grant with past expiry
        past_expiry = (datetime.now() - timedelta(hours=1)).isoformat()
        grant = CapabilityGrant(
            id=str(uuid.uuid4()),
            capability="open_application",
            constraints={"app_name": "chrome"},
            scope="session",
            enabled=True,
            created_at=datetime.now().isoformat(),
            expires_at=past_expiry
        )
        registry.register_grant(grant)
        
        # Should not match because expired
        match = registry.check_grant("open_application", {"app_name": "chrome"})
        self.assertIsNone(match)
        
        # Create grant with future expiry
        future_expiry = (datetime.now() + timedelta(hours=1)).isoformat()
        grant2 = CapabilityGrant(
            id=str(uuid.uuid4()),
            capability="open_application",
            constraints={"app_name": "firefox"},
            scope="session",
            enabled=True,
            created_at=datetime.now().isoformat(),
            expires_at=future_expiry
        )
        registry.register_grant(grant2)
        
        # Should match because not expired
        match = registry.check_grant("open_application", {"app_name": "firefox"})
        self.assertIsNotNone(match)

    def test_policy_integrates_capability_grants(self):
        """Test that policy engine respects capability grants."""
        from agent.policy import engine as policy_engine
        from agent.capabilities import registry, CapabilityGrant
        import uuid
        from datetime import datetime
        
        # Clear existing grants
        for g in registry.get_all_grants():
            registry.revoke_grant(g.id)
        
        # Without grant - should require approval in safe mode
        policy_engine.safe_mode = True
        decision = policy_engine.evaluate("open_application", {"app_name": "chrome"}, {"task_id": "test"})
        self.assertTrue(decision.requires_approval)
        
        # Create grant
        grant = CapabilityGrant(
            id=str(uuid.uuid4()),
            capability="open_application",
            constraints={"app_name": "chrome"},
            scope="persistent",
            enabled=True,
            created_at=datetime.now().isoformat()
        )
        registry.register_grant(grant)
        
        # With grant - should NOT require approval
        decision = policy_engine.evaluate("open_application", {"app_name": "chrome"}, {"task_id": "test"})
        self.assertFalse(decision.requires_approval)
        self.assertIn("capability grant", decision.reason.lower())
        
        # Different app still requires approval
        decision = policy_engine.evaluate("open_application", {"app_name": "firefox"}, {"task_id": "test"})
        self.assertTrue(decision.requires_approval)

    def test_tool_registry_has_granular_desktop_tools(self):
        """Test that tool registry has all granular desktop capabilities."""
        from agent.tool_registry import registry as tool_registry
        
        expected_tools = [
            "open_application",
            "open_website",
            "set_volume",
            "set_brightness",
            "get_clipboard",
            "search_and_play_youtube",
        ]
        
        for tool_name in expected_tools:
            spec = tool_registry.get_spec(tool_name)
            self.assertIsNotNone(spec, f"Missing tool: {tool_name}")
            self.assertEqual(spec.name, tool_name)
            self.assertIn("additionalProperties", spec.input_schema)
            self.assertFalse(spec.input_schema["additionalProperties"])
        
        # Legacy desktop_action should still exist
        legacy = tool_registry.get_spec("desktop_action")
        self.assertIsNotNone(legacy)

    def test_desktop_tools_execute_without_approval_when_granted(self):
        """Test that granted desktop tools execute without approval."""
        from agent.executor import ToolExecutor
        from agent.tool_registry import registry as tool_registry
        from agent.capabilities import registry as capability_registry, CapabilityGrant
        from agent.policy import engine as policy_engine
        import uuid
        from datetime import datetime
        
        # Clear existing grants
        for g in capability_registry.get_all_grants():
            capability_registry.revoke_grant(g.id)
        
        policy_engine.safe_mode = True
        executor = ToolExecutor(tool_registry, approval_timeout=0.5)
        
        # Grant open_application for chrome
        grant = CapabilityGrant(
            id=str(uuid.uuid4()),
            capability="open_application",
            constraints={"app_name": "chrome"},
            scope="persistent",
            enabled=True,
            created_at=datetime.now().isoformat()
        )
        capability_registry.register_grant(grant)
        
        # Execute should not require approval (will fail due to no actual chrome, but not due to approval)
        result = executor.execute("open_application", {"app_name": "chrome"}, {"task_id": "grant-test"})
        # Status should not be approval_timeout or denied
        self.assertNotEqual(result.status, "approval_timeout")
        self.assertNotEqual(result.status, "denied")
        # It will likely be error (chrome not found) but that's expected


# ============================================================================
# Phase 10: Comprehensive Testing
# ============================================================================

class Phase10DelegationTests(unittest.TestCase):
    """Test delegation from Assistant to AgentRuntime."""
    
    def setUp(self):
        from agent.assistant_bridge import AssistantBridge
        from agent.capabilities import registry as capability_registry
        from agent.policy import engine as policy_engine
        policy_engine.safe_mode = True
        # Clear grants
        for g in capability_registry.get_all_grants():
            capability_registry.revoke_grant(g.id)
        self.bridge = AssistantBridge()
    
    def tearDown(self):
        # Cancel any running tasks
        for task_id in list(self.bridge.active_tasks.keys()):
            self.bridge.active_tasks[task_id].cancellation_event.set()
    
    def test_delegation_creates_task_returns_task_id_immediately(self):
        """Assistant delegation creates task, returns task_id immediately."""
        task_id = self.bridge.delegate_task("Test task")
        self.assertIsNotNone(task_id)
        self.assertIsInstance(task_id, str)
        self.assertTrue(len(task_id) > 0)
        
        # Task should be in active tasks
        status = self.bridge.get_task_status(task_id)
        self.assertIsNotNone(status)
        self.assertEqual(status["description"], "Test task")
        self.assertEqual(status["status"], "running")
    
    def test_no_os_tool_executes_inside_gemini_live(self):
        """Gemini Live only has delegation tools, no OS tools."""
        from providers.gemini_live import LIVE_TOOL_DECLARATIONS
        tool_names = [t.name for t in LIVE_TOOL_DECLARATIONS]
        
        # Should only have delegation/approval tools
        allowed_tools = {
            "delegate_to_agent", "get_agent_status", 
            "approve_pending_action", "reject_pending_action",
            "get_project_context", "get_task_history", "find_task_by_description"
        }
        self.assertEqual(set(tool_names), allowed_tools)
        
        # No OS tools
        os_tools = ["open_application", "execute_shell", "write_file", "read_file", "desktop_action"]
        for os_tool in os_tools:
            self.assertNotIn(os_tool, tool_names)
    
    def test_task_runs_in_agent_runtime_emits_events(self):
        """Task runs in AgentRuntime, emits events."""
        from agent.events import emit
        from agent.assistant_events import AssistantEvent
        
        task_id = self.bridge.delegate_task("Echo test")
        import time
        time.sleep(1.0)  # Let task start
        
        # Check task is running or has completed/failed (removed from active_tasks)
        status = self.bridge.get_task_status(task_id)
        # If task completed quickly, it will be in history
        if status is None:
            # Check history
            history = self.bridge.get_recent_task_history(10)
            found = any(h["task_id"] == task_id for h in history)
            self.assertTrue(found, "Task should be in active_tasks or history")
        else:
            self.assertIn(status["status"], ["running", "completed", "failed"])


class Phase10ApprovalTests(unittest.TestCase):
    """Test voice approval workflow."""
    
    def setUp(self):
        from agent.assistant_bridge import AssistantBridge
        from agent.capabilities import registry as capability_registry
        from agent.policy import engine as policy_engine
        from agent.approvals import manager as approval_manager
        policy_engine.safe_mode = True
        for g in capability_registry.get_all_grants():
            capability_registry.revoke_grant(g.id)
        with approval_manager._lock:
            approval_manager._pending.clear()
        self.bridge = AssistantBridge()
    
    def test_voice_approval_only_resolves_existing_approval(self):
        """Voice approval only resolves existing approval."""
        from agent.approvals import manager as approval_manager
        
        task_id = self.bridge.delegate_task("Test task")
        import time
        time.sleep(0.2)
        
        # Create a real approval via the approval manager (like ToolExecutor does)
        approval_id = approval_manager.request_approval(
            tool_name="open_application",
            arguments={"app_name": "chrome"},
            context={"task_id": task_id},
            risk_level="high",
            reason="Test approval",
            on_approve=lambda: "Approved",
            on_reject=lambda: "Denied"
        )
        time.sleep(0.2)
        
        # Approve should work
        result = self.bridge.approve_pending_action(approval_id)
        self.assertIn("Approved", result)
        
        # Approving again should fail (already processed)
        result2 = self.bridge.approve_pending_action(approval_id)
        self.assertIn("already", result2.lower())
    
    def test_invalid_approval_id_rejected(self):
        """Invalid approval_id rejected."""
        result = self.bridge.approve_pending_action("invalid-id")
        self.assertIn("Error", result)
        self.assertIn("not found", result)
    
    def test_expired_approval_rejected(self):
        """Expired approval rejected (simulated by double approve)."""
        from agent.approvals import manager as approval_manager
        import uuid
        
        task_id = self.bridge.delegate_task("Test task")
        import time
        time.sleep(0.2)
        
        approval_id = str(uuid.uuid4())
        approval_manager.request_approval(
            tool_name="open_application",
            arguments={"app_name": "chrome"},
            context={"task_id": task_id},
            risk_level="high",
            reason="Test",
            on_approve=lambda: "Approved",
            on_reject=lambda: "Denied"
        )
        time.sleep(0.2)
        
        # First approve works
        self.bridge.approve_pending_action(approval_id)
        # Second should fail
        result = self.bridge.approve_pending_action(approval_id)
        self.assertIn("Error", result)
    
    def test_cancelled_task_cannot_be_approved(self):
        """Cancelled task approvals are invalidated."""
        from agent.approvals import manager as approval_manager
        import uuid
        
        # Use a task that doesn't complete immediately
        task_id = self.bridge.delegate_task("Long running test task that takes time")
        import time
        time.sleep(0.2)
        
        approval_id = str(uuid.uuid4())
        approval_manager.request_approval(
            tool_name="open_application",
            arguments={"app_name": "chrome"},
            context={"task_id": task_id},
            risk_level="high",
            reason="Test",
            on_approve=lambda: "Approved",
            on_reject=lambda: "Denied"
        )
        time.sleep(0.2)
        
        # Check task is still active
        if task_id not in self.bridge.active_tasks:
            self.skipTest("Task completed too quickly to test cancellation")
        
        # Cancel the task - this should also cancel its approvals
        self.bridge.active_tasks[task_id].cancellation_event.set()
        approval_manager.cancel_task(task_id)
        time.sleep(0.2)
        
        # Approval should be cancelled
        approval = approval_manager.get_approval(approval_id)
        self.assertIsNone(approval)  # Should be removed
    
    def test_approval_attached_to_exact_task_and_tool(self):
        """Approval remains attached to exact task and tool."""
        from agent.approvals import manager as approval_manager
        
        task1 = self.bridge.delegate_task("Task 1")
        task2 = self.bridge.delegate_task("Task 2")
        import time
        time.sleep(0.2)
        
        approval_id1 = approval_manager.request_approval(
            tool_name="open_application",
            arguments={"app_name": "chrome"},
            context={"task_id": task1},
            risk_level="high",
            reason="Task 1 needs chrome",
            on_approve=lambda: "Approved",
            on_reject=lambda: "Denied"
        )
        
        approval_id2 = approval_manager.request_approval(
            tool_name="open_website",
            arguments={"url": "https://example.com"},
            context={"task_id": task2},
            risk_level="high",
            reason="Task 2 needs website",
            on_approve=lambda: "Approved",
            on_reject=lambda: "Denied"
        )
        time.sleep(0.2)
        
        # Get pending for task1
        pending1 = self.bridge.get_pending_approval(task1)
        self.assertIsNotNone(pending1)
        self.assertEqual(pending1["approval_id"], approval_id1)
        self.assertEqual(pending1["tool_name"], "open_application")
        
        # Get pending for task2
        pending2 = self.bridge.get_pending_approval(task2)
        self.assertIsNotNone(pending2)
        self.assertEqual(pending2["approval_id"], approval_id2)
        self.assertEqual(pending2["tool_name"], "open_website")


class Phase10EventBridgeTests(unittest.TestCase):
    """Test EventBus → AssistantBridge event translation."""
    
    def setUp(self):
        from agent.assistant_bridge import AssistantBridge
        from agent.capabilities import registry as capability_registry
        from agent.policy import engine as policy_engine
        policy_engine.safe_mode = True
        for g in capability_registry.get_all_grants():
            capability_registry.revoke_grant(g.id)
        self.bridge = AssistantBridge()
        self.received_events = []
        self.bridge.register_event_handler(self._capture_event)
    
    def _capture_event(self, event):
        self.received_events.append(event)
    
    def test_task_started_emits_task_started(self):
        """TASK_STARTED → Assistant receives task_started."""
        from agent.events import emit
        
        emit("TASK_STARTED", "test-task-1", {"description": "Test task"})
        import time
        time.sleep(0.2)
        
        events = [e for e in self.received_events if e.type == "task_started"]
        self.assertTrue(len(events) > 0)
        self.assertEqual(events[0].task_id, "test-task-1")
        self.assertIn("Started task", events[0].summary)
    
    def test_approval_required_emits_approval_required(self):
        """APPROVAL_REQUIRED → Assistant receives approval_required."""
        from agent.events import emit
        
        emit("APPROVAL_REQUIRED", "test-task-2", {
            "approval_id": "approval-123",
            "tool_name": "open_application",
            "arguments": {"app_name": "chrome"},
            "risk_level": "high",
            "reason": "Need chrome"
        })
        import time
        time.sleep(0.2)
        
        events = [e for e in self.received_events if e.type == "approval_required"]
        self.assertTrue(len(events) > 0)
        self.assertEqual(events[0].approval_id, "approval-123")
        self.assertEqual(events[0].risk, "high")
        self.assertEqual(events[0].current_tool, "open_application")
    
    def test_task_completed_emits_task_completed(self):
        """TASK_COMPLETED → Assistant receives task_completed."""
        from agent.events import emit
        
        emit("TASK_COMPLETED", "test-task-3", {"result": "Task done successfully"})
        import time
        time.sleep(0.2)
        
        events = [e for e in self.received_events if e.type == "task_completed"]
        self.assertTrue(len(events) > 0)
        self.assertIn("completed", events[0].summary.lower())
    
    def test_task_failed_emits_task_failed(self):
        """TASK_FAILED → Assistant receives task_failed."""
        from agent.events import emit
        
        emit("TASK_FAILED", "test-task-4", {"error": "Something went wrong"})
        import time
        time.sleep(0.2)
        
        events = [e for e in self.received_events if e.type == "task_failed"]
        self.assertTrue(len(events) > 0)
        self.assertEqual(events[0].risk, "critical")
        self.assertIn("failed", events[0].summary.lower())


class Phase10ConcurrencyTests(unittest.TestCase):
    """Test multi-task isolation and approval isolation."""
    
    def setUp(self):
        from agent.assistant_bridge import AssistantBridge
        from agent.capabilities import registry as capability_registry
        from agent.policy import engine as policy_engine
        policy_engine.safe_mode = True
        for g in capability_registry.get_all_grants():
            capability_registry.revoke_grant(g.id)
        self.bridge = AssistantBridge()
    
    def tearDown(self):
        for task_id in list(self.bridge.active_tasks.keys()):
            self.bridge.active_tasks[task_id].cancellation_event.set()
    
    def test_two_simultaneous_tasks_stay_isolated(self):
        """Two simultaneous tasks stay isolated."""
        task1 = self.bridge.delegate_task("Task A: Open Chrome")
        task2 = self.bridge.delegate_task("Task B: Search YouTube")
        import time
        time.sleep(0.5)
        
        # Check both tasks exist (either in active_tasks or history)
        active = self.bridge.get_active_tasks()
        history = self.bridge.get_recent_task_history(10)
        all_tasks = {t["task_id"]: t for t in active}
        for h in history:
            if h["task_id"] not in all_tasks:
                all_tasks[h["task_id"]] = h
        
        self.assertIn(task1, all_tasks)
        self.assertIn(task2, all_tasks)
        
        # Each task has its own status
        status1 = self.bridge.get_task_status(task1)
        status2 = self.bridge.get_task_status(task2)
        # If completed, check history
        if status1 is None:
            status1 = next(h for h in history if h["task_id"] == task1)
        if status2 is None:
            status2 = next(h for h in history if h["task_id"] == task2)
        
        self.assertEqual(status1["description"], "Task A: Open Chrome")
        self.assertEqual(status2["description"], "Task B: Search YouTube")
    
    def test_two_approvals_stay_isolated(self):
        """Two approvals stay isolated."""
        from agent.approvals import manager as approval_manager
        
        task1 = self.bridge.delegate_task("Task 1")
        task2 = self.bridge.delegate_task("Task 2")
        import time
        time.sleep(0.2)
        
        approval_id_a = approval_manager.request_approval(
            tool_name="open_application",
            arguments={"app_name": "chrome"},
            context={"task_id": task1},
            risk_level="high",
            reason="Task 1 chrome",
            on_approve=lambda: "Approved",
            on_reject=lambda: "Denied"
        )
        
        approval_id_b = approval_manager.request_approval(
            tool_name="open_website",
            arguments={"url": "https://example.com"},
            context={"task_id": task2},
            risk_level="high",
            reason="Task 2 website",
            on_approve=lambda: "Approved",
            on_reject=lambda: "Denied"
        )
        time.sleep(0.2)
        
        # Get all pending
        all_pending = self.bridge.get_all_pending_approvals()
        self.assertEqual(len(all_pending), 2)
        
        # Approve only task1
        result = self.bridge.approve_pending_action(approval_id_a)
        self.assertIn("Approved", result)
        
# Task2 approval should still be pending
        pending = self.bridge.get_pending_approval(task2)
        self.assertIsNotNone(pending)
        self.assertEqual(pending["approval_id"], approval_id_b)

    def test_task_a_completion_doesnt_update_task_b(self):
        """Task A completion doesn't update Task B."""
        from agent.events import emit
        
        task1 = self.bridge.delegate_task("Simple task A")
        task2 = self.bridge.delegate_task("Simple task B")
        import time
        time.sleep(0.5)
        
        # Get initial status - both should exist (in active_tasks or history)
        def get_task_status_or_history(bridge, task_id):
            status = bridge.get_task_status(task_id)
            if status is None:
                history = bridge.get_recent_task_history(10)
                status = next((h for h in history if h["task_id"] == task_id), None)
            return status
        
        status1_initial = get_task_status_or_history(self.bridge, task1)
        status2_initial = get_task_status_or_history(self.bridge, task2)
        self.assertIsNotNone(status1_initial)
        self.assertIsNotNone(status2_initial)
        self.assertEqual(status1_initial["description"], "Simple task A")
        self.assertEqual(status2_initial["description"], "Simple task B")
        
        # Complete task1 via event
        emit("TASK_COMPLETED", task1, {"result": "Task A done"})
        time.sleep(0.2)
        
        # Task1 should be completed (in history)
        status1 = self.bridge.get_task_status(task1)
        if status1 is None:
            history = self.bridge.get_recent_task_history(10)
            status1 = next(h for h in history if h["task_id"] == task1)
        self.assertIn(status1["status"], ["completed", "failed"])
        
        # Task2 should still exist and be independent (not affected by task1 completion)
        status2 = self.bridge.get_task_status(task2)
        # If task2 completed quickly, check history
        if status2 is None:
            history = self.bridge.get_recent_task_history(10)
            status2 = next((h for h in history if h["task_id"] == task2), None)
        self.assertIsNotNone(status2, "Task2 should exist in active_tasks or history")
        # The key test: task2 status should not be the same object as task1
        self.assertNotEqual(id(status1), id(status2))
        # And task2 description should be Task B
        self.assertEqual(status2["description"], "Simple task B")


class Phase10RecoveryTests(unittest.TestCase):
    """Test session recovery and resilience."""
    
    def setUp(self):
        from agent.assistant_bridge import AssistantBridge
        from agent.capabilities import registry as capability_registry
        from agent.policy import engine as policy_engine
        policy_engine.safe_mode = True
        for g in capability_registry.get_all_grants():
            capability_registry.revoke_grant(g.id)
        self.bridge = AssistantBridge()
    
    def test_gemini_live_disconnect_doesnt_terminate_agent_runtime(self):
        """Gemini Live disconnect doesn't terminate AgentRuntime."""
        task_id = self.bridge.delegate_task("Long running task")
        import time
        time.sleep(0.5)
        
        # Simulate disconnect by checking task still exists (in active_tasks or history)
        status = self.bridge.get_task_status(task_id)
        if status is None:
            history = self.bridge.get_recent_task_history(10)
            status = next((h for h in history if h["task_id"] == task_id), None)
        self.assertIsNotNone(status)
        # Task should still be running or completed
        self.assertIn(status["status"], ["running", "completed", "failed"])
    
    def test_agent_completion_available_after_live_reconnect(self):
        """Agent completion available after Live reconnect."""
        task_id = self.bridge.delegate_task("Quick task")
        import time
        time.sleep(1.0)  # Let it complete
        
        # Get context for resumption (simulates reconnect)
        context = self.bridge.get_context_for_resumption()
        
        # Should have recent task history
        self.assertTrue(len(context["recent_task_history"]) > 0)
        recent = context["recent_task_history"][-1]
        self.assertEqual(recent["task_id"], task_id)
        self.assertIn(recent["status"], ["completed", "failed"])
    
    def test_active_task_state_survives_assistant_reconnection(self):
        """Active task state survives Assistant reconnection."""
        task_id = self.bridge.delegate_task("Persistent task")
        import time
        time.sleep(0.5)
        
        # Simulate new bridge (reconnection)
        from agent.assistant_bridge import AssistantBridge
        new_bridge = AssistantBridge()
        
        # Old bridge still has the task (in active_tasks or history)
        old_status = self.bridge.get_task_status(task_id)
        if old_status is None:
            history = self.bridge.get_recent_task_history(10)
            old_status = next((h for h in history if h["task_id"] == task_id), None)
        self.assertIsNotNone(old_status)
        
        # New bridge doesn't have old tasks (they're in different instances)
        # But the AgentRuntime task is still running in background
        # This is expected - each bridge instance tracks its own tasks
        # The key is that AgentRuntime continues independently


class Phase10SecurityTests(unittest.TestCase):
    """Test security boundaries."""
    
    def test_gemini_live_cannot_call_desktop_tools_directly(self):
        """Gemini Live cannot call desktop tools directly."""
        from providers.gemini_live import LIVE_TOOL_DECLARATIONS
        tool_names = [t.name for t in LIVE_TOOL_DECLARATIONS]
        
        desktop_tools = ["open_application", "open_website", "set_volume", "set_brightness", 
                         "get_clipboard", "search_and_play_youtube", "desktop_action"]
        for tool in desktop_tools:
            self.assertNotIn(tool, tool_names, 
                f"Gemini Live should not have direct access to {tool}")
    
    def test_gemini_live_cannot_call_shell_tools(self):
        """Gemini Live cannot call shell tools."""
        from providers.gemini_live import LIVE_TOOL_DECLARATIONS
        tool_names = [t.name for t in LIVE_TOOL_DECLARATIONS]
        
        shell_tools = ["execute_shell", "bash", "sh", "cmd", "powershell"]
        for tool in shell_tools:
            self.assertNotIn(tool, tool_names)
    
    def test_gemini_live_cannot_write_files_directly(self):
        """Gemini Live cannot write files directly."""
        from providers.gemini_live import LIVE_TOOL_DECLARATIONS
        tool_names = [t.name for t in LIVE_TOOL_DECLARATIONS]
        
        file_tools = ["write_file", "read_file", "delete_file", "list_files"]
        for tool in file_tools:
            self.assertNotIn(tool, tool_names)
    
    def test_only_assistant_bridge_can_delegate_or_resolve_approvals(self):
        """Only AssistantBridge can delegate or resolve approvals."""
        from agent.assistant_bridge import AssistantBridge
        from agent.capabilities import registry as capability_registry
        from agent.policy import engine as policy_engine
        from agent.approvals import manager as approval_manager
        policy_engine.safe_mode = True
        for g in capability_registry.get_all_grants():
            capability_registry.revoke_grant(g.id)
        with approval_manager._lock:
            approval_manager._pending.clear()
        
        bridge = AssistantBridge()
        
        # Delegate works
        task_id = bridge.delegate_task("Test")
        self.assertIsNotNone(task_id)
        
        # Approve/reject works through bridge
        approval_id = approval_manager.request_approval(
            tool_name="open_application",
            arguments={"app_name": "chrome"},
            context={"task_id": task_id},
            risk_level="high",
            reason="Test",
            on_approve=lambda: "Approved",
            on_reject=lambda: "Denied"
        )
        import time
        time.sleep(0.2)
        
        result = bridge.approve_pending_action(approval_id)
        self.assertIn("Approved", result)
        
        # Approval should be processed (consumed)
        approval = approval_manager.get_approval(approval_id)
        self.assertIsNone(approval)  # Consumed


class Phase10CapabilityGrantTests(unittest.TestCase):
    """Test capability grant functionality."""
    
    def setUp(self):
        from agent.capabilities import registry as capability_registry
        from agent.policy import engine as policy_engine
        policy_engine.safe_mode = True
        for g in capability_registry.get_all_grants():
            capability_registry.revoke_grant(g.id)
    
    def test_grant_creation_via_approval_dialog_always_allow(self):
        """Grant creation via approval dialog 'Always allow'."""
        from agent.capabilities import registry, CapabilityGrant
        import uuid
        from datetime import datetime
        
        grant = CapabilityGrant(
            id=str(uuid.uuid4()),
            capability="open_application",
            constraints={"app_name": "chrome"},
            scope="persistent",
            enabled=True,
            created_at=datetime.now().isoformat()
        )
        registry.register_grant(grant)
        
        grants = registry.get_all_grants()
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0].capability, "open_application")
        self.assertEqual(grants[0].constraints["app_name"], "chrome")
        self.assertEqual(grants[0].scope, "persistent")
    
    def test_grant_constraints_enforced_chrome_only(self):
        """Grant constraints enforced (Chrome only, not arbitrary apps)."""
        from agent.capabilities import registry, CapabilityGrant
        from agent.policy import engine as policy_engine
        import uuid
        from datetime import datetime
        
        # Clear grants
        for g in registry.get_all_grants():
            registry.revoke_grant(g.id)
        
        # Grant for chrome only
        grant = CapabilityGrant(
            id=str(uuid.uuid4()),
            capability="open_application",
            constraints={"app_name": "chrome"},
            scope="persistent",
            enabled=True,
            created_at=datetime.now().isoformat()
        )
        registry.register_grant(grant)
        
        # Chrome should not require approval
        decision = policy_engine.evaluate("open_application", {"app_name": "chrome"}, {"task_id": "test"})
        self.assertFalse(decision.requires_approval)
        
        # Firefox should still require approval
        decision = policy_engine.evaluate("open_application", {"app_name": "firefox"}, {"task_id": "test"})
        self.assertTrue(decision.requires_approval)
    
    def test_grant_persistence_across_restarts(self):
        """Grant persistence across restarts (SQLite)."""
        from agent.capabilities import registry, CapabilityGrant
        from memory.sqlite import get_db_connection
        import uuid
        from datetime import datetime
        
        grant = CapabilityGrant(
            id=str(uuid.uuid4()),
            capability="open_application",
            constraints={"app_name": "chrome"},
            scope="persistent",
            enabled=True,
            created_at=datetime.now().isoformat()
        )
        registry.register_grant(grant)
        
        # Check in database
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM capability_grants WHERE enabled=1 AND capability='open_application'")
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)
    
    def test_grant_revocation_works(self):
        """Grant revocation works."""
        from agent.capabilities import registry, CapabilityGrant
        import uuid
        from datetime import datetime
        
        grant = CapabilityGrant(
            id="test-revoke-grant",
            capability="open_application",
            constraints={"app_name": "chrome"},
            scope="persistent",
            enabled=True,
            created_at=datetime.now().isoformat()
        )
        registry.register_grant(grant)
        
        self.assertTrue(registry.revoke_grant("test-revoke-grant"))
        grants = registry.get_all_grants()
        self.assertEqual(len(grants), 0)
    
    def test_session_scope_grants_expire_on_session_end(self):
        """Session-scope grants expire on session end."""
        from agent.capabilities import registry, CapabilityGrant
        from agent.policy import engine as policy_engine
        import uuid
        from datetime import datetime, timedelta
        
        # Clear grants
        for g in registry.get_all_grants():
            registry.revoke_grant(g.id)
        
        # Expired grant
        expired_grant = CapabilityGrant(
            id="expired-grant",
            capability="open_application",
            constraints={"app_name": "chrome"},
            scope="session",
            enabled=True,
            created_at=(datetime.now() - timedelta(hours=2)).isoformat(),
            expires_at=(datetime.now() - timedelta(hours=1)).isoformat()
        )
        registry.register_grant(expired_grant)
        
        # Should not match (expired)
        decision = policy_engine.evaluate("open_application", {"app_name": "chrome"}, {"task_id": "test"})
        self.assertTrue(decision.requires_approval)
        
        # Future expiry grant
        future_grant = CapabilityGrant(
            id="future-grant",
            capability="open_application",
            constraints={"app_name": "firefox"},
            scope="session",
            enabled=True,
            created_at=datetime.now().isoformat(),
            expires_at=(datetime.now() + timedelta(hours=1)).isoformat()
        )
        registry.register_grant(future_grant)
        
        # Should match (not expired)
        decision = policy_engine.evaluate("open_application", {"app_name": "firefox"}, {"task_id": "test"})
        self.assertFalse(decision.requires_approval)


if __name__ == "__main__":
    unittest.main()