import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.policy import engine as policy_engine
from agent.executor import ToolExecutor
from agent.tool_registry import registry
from agent.vertical_slice import VerticalSliceRunner


class VerticalSliceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="guru-m3-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        (self.root / "tests").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "math.py").write_text("# TODO: implement add\n", encoding="utf-8")
        self.expected = 5
        self.write_test()

        self.original_safe_mode = policy_engine.safe_mode
        self.original_audit = policy_engine.audit_file
        policy_engine.safe_mode = False
        policy_engine.audit_file = Path(self.temp.name) / "security_audit.log"
        self.addCleanup(setattr, policy_engine, "safe_mode", self.original_safe_mode)
        self.addCleanup(setattr, policy_engine, "audit_file", self.original_audit)
        self.runner = VerticalSliceRunner(ToolExecutor(registry))

    def write_test(self):
        (self.root / "tests" / "test_math.py").write_text(
            "import importlib.util\nfrom pathlib import Path\n\n"
            "_path = Path(__file__).resolve().parents[1] / 'math.py'\n"
            "_spec = importlib.util.spec_from_file_location('repo_math', _path)\n"
            "_math = importlib.util.module_from_spec(_spec)\n"
            "_spec.loader.exec_module(_math)\n\n"
            "def test_add():\n"
            f"    assert _math.add(2, 3) == {self.expected}\n",
            encoding="utf-8",
        )

    def test_plan_action_and_verification_run_in_selected_repository(self):
        goal = "add a function add(a, b) to math.py and a test"
        with patch("agent.vertical_slice.get_active_project", return_value=self.root):
            with patch.object(policy_engine, "evaluate", wraps=policy_engine.evaluate) as evaluate:
                result = self.runner.run(goal)

        self.assertTrue(result.ok, result.summary)
        self.assertEqual(len(result.plan.steps), 1)
        self.assertIn("replace_in_file math.py", result.plan.steps[0])
        self.assertIn("def add(a, b):", (self.root / "math.py").read_text(encoding="utf-8"))
        self.assertTrue(result.action.ok)
        self.assertTrue(result.action.changed)
        self.assertTrue(result.verification.ok)
        self.assertEqual(result.repository, self.root.resolve())
        import json
        self.assertEqual(json.loads(result.verification.artifact)["cwd"], str(self.root.resolve()))
        self.assertEqual([call.args[0] for call in evaluate.call_args_list], ["replace_in_file", "run_command"])

    def test_failed_verification_reports_failure(self):
        self.expected = 6
        self.write_test()

        result = self.runner.run(
            "add a function add(a, b) to math.py and a test", repo_path=self.root
        )

        self.assertFalse(result.ok)
        self.assertTrue(result.action.ok)
        self.assertFalse(result.verification.ok)
        self.assertIn("1 failed", result.verification.details)

    def test_missing_project_fails_without_falling_back_to_guru_source(self):
        with patch("agent.vertical_slice.get_active_project", return_value=None):
            result = self.runner.run("add a function add(a, b) to math.py and a test")

        self.assertFalse(result.ok)
        self.assertIsNone(result.repository)
        self.assertIn("active project", result.summary.lower())
        self.assertEqual((self.root / "math.py").read_text(encoding="utf-8"), "# TODO: implement add\n")


if __name__ == "__main__":
    unittest.main()
