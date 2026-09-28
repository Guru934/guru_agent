import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


class ActiveProjectTests(unittest.TestCase):
    def setUp(self):
        from memory import sqlite as memory

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.db_path = self.home / ".local/share/guru_agent/history.db"
        self.db_path.parent.mkdir(parents=True)
        self.db_patch = patch.object(memory, "DB_PATH", self.db_path)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        memory.init_db()

    def _repo(self, name="repo"):
        repo = self.home / name
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        return repo

    def test_set_and_get_active_project(self):
        from memory.sqlite import get_active_project, set_active_project

        repo = self._repo()
        self.assertEqual(set_active_project(str(repo)), repo.resolve())
        self.assertEqual(get_active_project(), repo.resolve())

    def test_active_project_persists_across_fresh_process(self):
        from memory.sqlite import set_active_project

        repo = self._repo()
        set_active_project(str(repo))
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        result = subprocess.run(
            [sys.executable, "-c", "from memory.sqlite import get_active_project; print(get_active_project())"],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.strip(), str(repo.resolve()))

    def test_invalid_project_is_rejected(self):
        from memory.sqlite import set_active_project

        with self.assertRaisesRegex((ValueError, OSError), "(?i)(exist|repository|directory|project)"):
            set_active_project(str(self.home / "missing"))

    def test_guru_agent_source_tree_is_not_a_selectable_project(self):
        from config import APP_DIR
        from memory.sqlite import set_active_project

        with self.assertRaises(ValueError):
            set_active_project(str(APP_DIR))

    def test_explicit_repo_path_is_used_by_delegated_task(self):
        from agent.assistant_bridge import AssistantBridge

        repo = self._repo()
        started = threading.Event()
        with patch("agent.assistant_bridge.AgentRuntime") as runtime_cls:
            runtime_cls.return_value.run.side_effect = lambda **kwargs: started.set()
            bridge = AssistantBridge()
            task_id = bridge.delegate_task("Update source code", repo_path=str(repo))
            self.assertTrue(started.wait(2))
            runtime_cls.assert_called_once_with(
                model_id="gemini-2.5-flash", project_path=repo.resolve(), require_project=True
            )
            self.assertTrue(task_id)

    def test_omitted_repo_path_uses_active_project(self):
        from agent.assistant_bridge import AssistantBridge
        from memory.sqlite import set_active_project

        repo = self._repo()
        set_active_project(str(repo))
        started = threading.Event()
        with patch("agent.assistant_bridge.AgentRuntime") as runtime_cls:
            runtime_cls.return_value.run.side_effect = lambda **kwargs: started.set()
            task_id = AssistantBridge().delegate_task("Fix source code")
            self.assertTrue(started.wait(2))
            runtime_cls.assert_called_once_with(
                model_id="gemini-2.5-flash", project_path=repo.resolve(), require_project=True
            )
            self.assertTrue(task_id)

    def test_explicit_repo_path_takes_precedence_over_active_project(self):
        from agent.assistant_bridge import AssistantBridge
        from memory.sqlite import set_active_project

        active_repo = self._repo("active")
        explicit_repo = self._repo("explicit")
        set_active_project(str(active_repo))
        started = threading.Event()
        with patch("agent.assistant_bridge.AgentRuntime") as runtime_cls:
            runtime_cls.return_value.run.side_effect = lambda **kwargs: started.set()
            task_id = AssistantBridge().delegate_task("Fix code", repo_path=str(explicit_repo))
            self.assertTrue(started.wait(2))
            runtime_cls.assert_called_once_with(
                model_id="gemini-2.5-flash",
                project_path=explicit_repo.resolve(),
                require_project=True,
            )
            self.assertTrue(task_id)

    def test_coding_task_without_project_does_not_fall_back_to_source_tree(self):
        from agent.assistant_bridge import AssistantBridge

        with patch("agent.assistant_bridge.AgentRuntime") as runtime_cls:
            with self.assertRaisesRegex(ValueError, "(?i)(active project|repo_path|project)"):
                AssistantBridge().delegate_task("Fix the code in this repository")
            runtime_cls.assert_not_called()

    def test_existing_non_coding_delegation_behavior_is_preserved(self):
        from agent.assistant_bridge import AssistantBridge

        started = threading.Event()
        with patch("agent.assistant_bridge.AgentRuntime") as runtime_cls:
            runtime_cls.return_value.run.side_effect = lambda **kwargs: started.set()
            task_id = AssistantBridge().delegate_task("Open the calculator")
            self.assertTrue(started.wait(2))
            runtime_cls.assert_called_once_with(
                model_id="gemini-2.5-flash", project_path=None, require_project=True
            )
            self.assertTrue(task_id)

    def test_selected_project_is_the_tool_workspace(self):
        from agent.executor import ToolExecutor
        from agent.tool_registry import registry
        from config import APP_DIR
        from agent.policy import engine as policy_engine

        repo = self._repo()
        original_safe_mode = policy_engine.safe_mode
        original_audit = policy_engine.audit_file
        policy_engine.safe_mode = False
        policy_engine.audit_file = self.home / "security_audit.log"
        self.addCleanup(setattr, policy_engine, "safe_mode", original_safe_mode)
        self.addCleanup(setattr, policy_engine, "audit_file", original_audit)
        executor = ToolExecutor(registry)
        result = executor.execute(
            "write_file", {"path": "created.txt", "content": "project"},
            {"task_id": "m1-test", "workspace_dir": repo},
        )
        self.assertEqual(result.status, "success")
        self.assertEqual((repo / "created.txt").read_text(), "project")
        self.assertFalse((APP_DIR / "created.txt").exists())
        denied = executor.execute(
            "read_file", {"path": str(APP_DIR / "config.py")},
            {"task_id": "m1-test", "workspace_dir": repo},
        )
        self.assertEqual(denied.status, "denied")

    def test_delegated_repository_tools_are_blocked_without_project(self):
        from agent.executor import ToolExecutor
        from agent.tool_registry import registry
        from agent.policy import engine as policy_engine

        executor = ToolExecutor(registry)
        context = {"task_id": "m1-no-project", "require_project": True}
        calls = [
            ("read_file", {"path": "config.py"}),
            ("write_file", {"path": "new_file.py", "content": "x"}),
            ("search", {"query": "APP_DIR"}),
            ("execute_shell", {"command": "echo can-write-by-python"}),
        ]
        with patch.object(policy_engine, "_log_audit", return_value=True):
            for tool_name, arguments in calls:
                with self.subTest(tool_name=tool_name):
                    result = executor.execute(tool_name, arguments, context)
                    self.assertEqual(result.status, "denied")
                    self.assertIn("selected active project", str(result.output))

    def test_assistant_exposes_project_selection_and_show_tools(self):
        from providers.gemini_live import LIVE_TOOL_DECLARATIONS

        names = {declaration.name for declaration in LIVE_TOOL_DECLARATIONS}
        self.assertIn("set_active_project", names)
        self.assertIn("get_active_project", names)
        delegate = next(item for item in LIVE_TOOL_DECLARATIONS if item.name == "delegate_to_agent")
        self.assertIn("repo_path", delegate.parameters.properties)

    def test_project_cli_use_and_show(self):
        repo = self._repo()
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        cli = Path(__file__).resolve().parents[1] / "guru"
        use = subprocess.run(
            [str(cli), "project", "use", str(repo)],
            cwd=self.home,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        show = subprocess.run(
            [str(cli), "project", "show"],
            cwd=self.home,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        expected = f"Active project: {repo.resolve()}"
        self.assertEqual(use.stdout.strip(), expected)
        self.assertEqual(show.stdout.strip(), expected)


if __name__ == "__main__":
    unittest.main()
