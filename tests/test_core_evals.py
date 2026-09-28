import unittest
import threading
import tempfile
from unittest.mock import patch, MagicMock
from pathlib import Path
import os
import sys

# Ensure components match context boundaries
from agent.policy import engine as policy_engine, PolicyDecision
from agent.executor import ToolExecutor, ExecutionResult
from agent.tool_registry import registry
from agent.approvals import manager as approval_manager
from agent.runtime import AgentRuntime
from agent.state import TaskState
from config import APP_DIR, DB_PATH

class CoreEvaluationSuite(unittest.TestCase):
    """
    Deterministic regression checks for workspace policy, agent runtime,
    and asynchronous GUI <-> Background tool blocking executes transactionally.
    """

    def setUp(self):
        # Guarantee safe mode is uniformly enabled for the tests
        policy_engine.safe_mode = True
        audit_dir = tempfile.TemporaryDirectory()
        original_audit_file = policy_engine.audit_file
        policy_engine.audit_file = Path(audit_dir.name) / "security_audit.log"
        self.addCleanup(setattr, policy_engine, "audit_file", original_audit_file)
        self.addCleanup(audit_dir.cleanup)

    def test_eval_01_policy_deny_destructive_commands(self):
        # Scenario: Threat agent attempts to bypass constraints via standard tool execution shell
        decision = policy_engine.evaluate(
            tool_name="execute_shell",
            arguments={"command": "rm -rf /"},
            context={}
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.risk_level.lower(), "critical")

        decision = policy_engine.evaluate(
            tool_name="execute_shell",
            arguments={"command": "sudo chown -R 777 /"},
            context={}
        )
        self.assertFalse(decision.allowed)

    def test_eval_02_policy_safe_commands_are_frictionless(self):
        # Scenario: Read-only diagnostics should execute instantaneously without UI blocks
        decision = policy_engine.evaluate(
            tool_name="execute_shell",
            arguments={"command": "ls -la"},
            context={}
        )
        self.assertTrue(decision.allowed)
        self.assertFalse(decision.requires_approval)
        self.assertEqual(decision.risk_level.lower(), "low")

    def test_eval_03_policy_install_triggers_manual_approval(self):
        # Scenario: Modifying environment dependencies forces the execution bridge to halt
        decision = policy_engine.evaluate(
            tool_name="execute_shell",
            arguments={"command": "npm install"},
            context={}
        )
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_approval) # Blocks UI

    def test_eval_04_policy_workspace_confinement(self):
        # Scenario: Data exfiltration attempts outside project domains are blocked natively
        decision = policy_engine.evaluate(
            tool_name="read_file",
            arguments={"path": "/etc/shadow"},
            context={}
        )
        self.assertFalse(decision.allowed)

        decision = policy_engine.evaluate(
            tool_name="write_file",
            arguments={"path": os.path.expanduser("~/.ssh/id_rsa.pub")},
            context={}
        )
        self.assertFalse(decision.allowed)

    def test_eval_05_policy_workspace_permitted(self):
        # Scenario: Local reads within boundaries trigger naturally based on risk configurations
        decision = policy_engine.evaluate(
            tool_name="read_file",
            arguments={"path": str(Path(__file__).parent.absolute())},
            context={}
        )
        self.assertTrue(decision.allowed)
        self.assertFalse(decision.requires_approval) # low risk reads

    def test_m0_policy_denies_writes_to_guru_source_tree(self):
        decision = policy_engine.evaluate(
            "write_file", {"path": str(APP_DIR / "config.py"), "content": "changed"}, {}
        )
        self.assertFalse(decision.allowed)
        self.assertIn("protected", decision.reason.lower())

    def test_m0_policy_allows_writes_to_another_workspace_root(self):
        with tempfile.TemporaryDirectory() as workspace:
            from config import WORKSPACE_ROOTS
            WORKSPACE_ROOTS.append(Path(workspace))
            self.addCleanup(WORKSPACE_ROOTS.remove, Path(workspace))
            decision = policy_engine.evaluate(
                "write_file", {"path": str(Path(workspace) / "notes.txt"), "content": "ok"}, {}
            )
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_approval)

    def test_m0_policy_denies_source_file_hard_link_in_allowed_workspace(self):
        from config import WORKSPACE_ROOTS

        with tempfile.TemporaryDirectory(dir=APP_DIR) as source_dir:
            with tempfile.TemporaryDirectory(dir=APP_DIR.parent) as workspace:
                source_file = Path(source_dir) / "source_module.py"
                hard_link = Path(workspace) / "source_module.py"
                source_file.write_text("source content", encoding="utf-8")
                try:
                    os.link(source_file, hard_link)
                except (OSError, NotImplementedError) as error:
                    self.skipTest(f"Filesystem cannot create hard links: {error}")

                workspace_root = Path(workspace)
                WORKSPACE_ROOTS.append(workspace_root)
                try:
                    decision = policy_engine.evaluate(
                        "write_file", {"path": str(hard_link), "content": "changed"}, {}
                    )
                finally:
                    WORKSPACE_ROOTS.remove(workspace_root)

        self.assertFalse(decision.allowed)
        self.assertIn("protected", decision.reason.lower())

    def test_m0_policy_denies_writes_to_history_database(self):
        decision = policy_engine.evaluate(
            "write_file", {"path": str(DB_PATH), "content": "changed"}, {}
        )
        self.assertFalse(decision.allowed)
        self.assertIn("protected", decision.reason.lower())

    def test_m0_policy_denies_writes_to_security_audit_log(self):
        from config import USER_STATE_DIR
        audit_path = USER_STATE_DIR / "security_audit.log"
        decision = policy_engine.evaluate(
            "write_file", {"path": str(audit_path), "content": "changed"}, {}
        )
        self.assertFalse(decision.allowed)
        self.assertIn("protected", decision.reason.lower())

    def test_eval_06_executor_intercepts_denials(self):
        # Scenario: Bypass of policy directly into Executor yields trapped Denial result
        executor = ToolExecutor(registry)
        result = executor.execute("execute_shell", {"command": "mkfs /dev/sda"}, {"task_id": "eval"})
        self.assertEqual(result.status, "denied")

    def test_eval_07_executor_approvals_block_until_granted(self):
        # Scenario: High-risk scripts block background operations utilizing async UI Thread locking
        executor = ToolExecutor(registry)

        # We need a thread to simulate the background orchestrator while the main thread acts like the Qt UI
        def _execute_in_background():
            return executor.execute("execute_shell", {"command": "pip install reqs"}, {"task_id": "eval_7"})

        # Hook the registry temporarily to mock shell avoiding actual installs on the tester's machine
        original_handler = registry.get_tool("execute_shell")
        try:
            registry._tools["execute_shell"].handler = lambda command: "installed!"

            # Start background tool execution
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_execute_in_background)

                # We need to wait momentarily until the executor registers the approval via manager
                import time; time.sleep(0.05)

                # Fetch pending approvals acting natively as the UI Application
                pending = list(approval_manager._pending.keys())
                self.assertEqual(len(pending), 1)

                approval_manager.approve(pending[0])

                # After UI resolution the thread should immediately unblock
                result = future.result(timeout=1.0)

            self.assertEqual(result.status, "success")
            self.assertEqual(result.output, "installed!")
        finally:
            registry._tools["execute_shell"].handler = original_handler

    def test_eval_08_executor_approvals_rejected(self):
        # Scenario: High-risk scripts rejected explicitly via UI drops the block and halts tool context
        executor = ToolExecutor(registry)

        def _execute_in_background():
            return executor.execute("execute_shell", {"command": "npm install test"}, {"task_id": "eval_8"})

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_execute_in_background)
            import time; time.sleep(0.05)

            pending = list(approval_manager._pending.keys())
            self.assertEqual(len(pending), 1)

            approval_manager.reject(pending[0]) # User explicitly aborted execution
            result = future.result(timeout=1.0)

        self.assertEqual(result.status, "denied")
        self.assertIn("explicitly denied", str(result.output))

    def test_eval_09_tool_schemas_locked_safely(self):
        # Scenario: Gemini FunctionDeclarations map firmly against our hard-coded specifications
        spec = registry.get_spec("execute_shell")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.risk, "high")
        self.assertIn("command", spec.input_schema["properties"])

    def test_eval_10_runtime_cancellation_terminates_loop(self):
        # Scenario: If User hits Cancel button, ReAct step processing cuts infinite generation explicitly
        runtime = AgentRuntime(model_id="ollama-test")

        # Emulate a loop cancellation instantly
        task_id = "cancel_eval_10"
        cancellation = threading.Event()
        cancellation.set()

        with patch('agent.runtime.create_agent_session') as create_session:
            state = runtime.run("Start working", task_id=task_id, cancellation_event=cancellation)
        create_session.assert_not_called()
        self.assertEqual(state.error, "Task cancelled by user.")
        self.assertTrue(state.completed)

    @patch('agent.runtime.create_agent_session')
    def test_eval_11_runtime_max_steps_halts_infinite_loops(self, create_session):
        # Scenario: Gemini bugs out and gets stuck looping identical `ls` operations forever. We halt at max.
        runtime = AgentRuntime()

        # Generate an adversarial response that infinitely calls functions
        from agent.model_provider import AgentFunctionCall, AgentResponse

        bad_response = AgentResponse(
            text="",
            function_calls=[AgentFunctionCall(name="search", arguments={"query": "test"})],
        )
        fake_session = MagicMock()
        fake_session.send_message.return_value = bad_response
        fake_session.send_tool_results.return_value = bad_response
        create_session.return_value = fake_session
        runtime.executor.execute = MagicMock(return_value=ExecutionResult("success", "matched"))

        state = runtime.run("Begin infinite loop")
        # Ensure we safely terminate and report it
        self.assertIn("exceeded maximum steps", str(state.error))
        self.assertTrue(state.completed)
        self.assertEqual(state.step_count, state.max_steps)

if __name__ == "__main__":
    unittest.main()
