import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.executor import ToolExecutor
from agent.policy import engine as policy_engine
from agent.tool_registry import registry
from agent.verifier import Verifier
from config import APP_DIR


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="guru-m4-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

        self.original_safe_mode = policy_engine.safe_mode
        self.original_audit = policy_engine.audit_file
        policy_engine.safe_mode = False
        policy_engine.audit_file = Path(self.temp.name) / "security_audit.log"
        self.addCleanup(setattr, policy_engine, "safe_mode", self.original_safe_mode)
        self.addCleanup(setattr, policy_engine, "audit_file", self.original_audit)
        self.executor = ToolExecutor(registry)
        self.verifier = Verifier(self.executor)

    def test_timeout_configuration_must_be_finite_and_within_tool_limit(self):
        for value in (0, float("inf"), float("nan"), 301, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Verifier(self.executor, timeout_seconds=value)

    def python_project(self, test_source="def test_ok():\n    assert True\n", config=""):
        (self.root / "pyproject.toml").write_text(
            "[project]\nname = 'verifier-fixture'\nversion = '0.1.0'\n" + config,
            encoding="utf-8",
        )
        tests = self.root / "tests"
        tests.mkdir(exist_ok=True)
        (tests / "test_sample.py").write_text(test_source, encoding="utf-8")

    def test_python_pytest_detection_and_pass(self):
        self.python_project()
        detected = self.verifier.detect_commands(self.root)
        self.assertIn("pytest", [command.name for command in detected])

        with patch.object(policy_engine, "evaluate", wraps=policy_engine.evaluate) as evaluate:
            with patch("agent.verifier.get_active_project", return_value=self.root):
                verdict = self.verifier.check("verify Python change", None)

        self.assertTrue(verdict.passed, verdict.summary)
        self.assertEqual(len(verdict.attempts), 1)
        self.assertEqual(verdict.attempts[0].commands[0].exit_status, 0)
        self.assertEqual([call.args[0] for call in evaluate.call_args_list], ["run_command"])
        self.assertEqual(evaluate.call_args.args[1]["cwd"], str(self.root.resolve()))

    def test_python_pytest_failure_is_retried_once_and_recorded(self):
        self.python_project("def test_failure():\n    assert False, 'expected fixture failure'\n")

        verdict = self.verifier.check("verify failing change", self.root)

        self.assertFalse(verdict.passed)
        self.assertTrue(verdict.retried)
        self.assertEqual(len(verdict.attempts), 2)
        for attempt in verdict.attempts:
            self.assertEqual(attempt.commands[0].exit_status, 1)
            self.assertIn("expected fixture failure", attempt.commands[0].output)

    def test_configured_ruff_and_mypy_are_detected_when_available(self):
        self.python_project(
            config="\n[tool.ruff]\nline-length = 88\n\n[tool.mypy]\nstrict = true\n"
        )
        with patch("agent.verifier.shutil.which", side_effect=lambda name: f"/tools/{name}"):
            detected = self.verifier.detect_commands(self.root)

        names = [command.name for command in detected]
        self.assertIn("ruff", names)
        self.assertIn("mypy", names)

    def test_missing_configured_optional_tool_is_a_clear_failure_not_a_pass(self):
        self.python_project(config="\n[tool.mypy]\nstrict = true\n")
        with patch("agent.verifier.shutil.which", return_value=None):
            verdict = self.verifier.check("verify typed code", self.root)

        self.assertFalse(verdict.passed)
        self.assertIn("mypy", " ".join(verdict.detection_errors).lower())
        self.assertEqual(verdict.attempts, ())

    def test_missing_pytest_does_not_report_pass(self):
        self.python_project()
        with patch("agent.verifier.importlib.util.find_spec", return_value=None), patch(
            "agent.verifier.shutil.which", return_value=None
        ):
            verdict = self.verifier.check("verify tests", self.root)

        self.assertFalse(verdict.passed)
        self.assertIn("pytest", " ".join(verdict.detection_errors).lower())

    def test_node_package_test_script_detection_and_success(self):
        if not shutil.which("node") or not shutil.which("npm"):
            self.skipTest("Node.js and npm are required for this Node verifier test.")
        (self.root / "package.json").write_text(
            json.dumps({"scripts": {"test": "node test.js", "lint": "node lint.js"}}),
            encoding="utf-8",
        )
        (self.root / "test.js").write_text("console.log('node test passed')\n", encoding="utf-8")
        (self.root / "lint.js").write_text("console.log('node lint passed')\n", encoding="utf-8")

        commands = self.verifier.detect_commands(self.root)
        self.assertEqual([command.name for command in commands], ["npm run test", "npm run lint"])
        verdict = self.verifier.check("verify node code", self.root)
        self.assertTrue(verdict.passed, verdict.summary)
        self.assertEqual([command.exit_status for command in verdict.attempts[0].commands], [0, 0])

    def test_node_failing_test_script_returns_failure(self):
        if not shutil.which("node") or not shutil.which("npm"):
            self.skipTest("Node.js and npm are required for this Node verifier test.")
        (self.root / "package.json").write_text(
            json.dumps({"scripts": {"test": "node test.js"}}), encoding="utf-8"
        )
        (self.root / "test.js").write_text("console.error('node test failed'); process.exit(3)\n", encoding="utf-8")

        verdict = self.verifier.check("verify node code", self.root)

        self.assertFalse(verdict.passed)
        self.assertTrue(verdict.retried)
        self.assertEqual(verdict.attempts[-1].commands[0].exit_status, 3)
        self.assertIn("node test failed", verdict.attempts[-1].commands[0].output)

    def test_rust_commands_are_detected_when_available(self):
        (self.root / "Cargo.toml").write_text("[package]\nname='fixture'\nversion='0.1.0'\nedition='2021'\n")
        with patch("agent.verifier.shutil.which", side_effect=lambda name: f"/tools/{name}"):
            commands = self.verifier.detect_commands(self.root)
        self.assertEqual([command.name for command in commands], ["cargo test", "cargo clippy"])

    def test_rust_project_tests_skip_clearly_or_report_pass_and_fail(self):
        if not shutil.which("cargo") or not shutil.which("cargo-clippy"):
            self.skipTest("Rust cargo and cargo-clippy toolchain is unavailable in this environment.")
        (self.root / "Cargo.toml").write_text(
            "[package]\nname='fixture'\nversion='0.1.0'\nedition='2021'\n"
        )
        (self.root / "src").mkdir()
        (self.root / "src" / "lib.rs").write_text("#[test]\nfn works() { assert!(true); }\n")
        self.assertTrue(self.verifier.check("verify Rust code", self.root).passed)
        (self.root / "src" / "lib.rs").write_text("#[test]\nfn fails() { assert!(false); }\n")
        failed = self.verifier.check("verify failing Rust code", self.root)
        self.assertFalse(failed.passed)
        self.assertTrue(failed.retried)

    def test_cwd_is_selected_repo_and_model_step_is_never_shell_input(self):
        self.python_project()
        hostile_step = "run pytest; touch SHOULD_NOT_EXIST $(id)"
        with patch.object(policy_engine, "evaluate", wraps=policy_engine.evaluate) as evaluate:
            verdict = self.verifier.check(hostile_step, self.root)

        self.assertTrue(verdict.passed)
        arguments = evaluate.call_args.args[1]
        self.assertIsInstance(arguments["argv"], list)
        self.assertEqual(arguments["cwd"], str(self.root.resolve()))
        self.assertFalse((self.root / "SHOULD_NOT_EXIST").exists())
        self.assertNotIn(hostile_step, " ".join(arguments["argv"]))

    def test_outside_cwd_is_rejected_by_executor_policy(self):
        result = self.executor.execute(
            "run_command",
            {"argv": ["/usr/bin/true"], "cwd": str(self.root.parent), "timeout": 2},
            {"task_id": "m4-outside-cwd", "workspace_dir": self.root, "require_project": True},
        )
        self.assertEqual(result.status, "denied")

    def test_guru_source_is_rejected_without_verification_execution(self):
        self.python_project()
        with patch.object(self.executor, "execute", wraps=self.executor.execute) as execute:
            with patch("agent.verifier.get_active_project", return_value=self.root):
                guru = self.verifier.check("verify", APP_DIR)
        self.assertFalse(guru.passed)
        self.assertEqual(execute.call_count, 0)

    def test_missing_active_project_fails_without_falling_back(self):
        with patch("agent.verifier.get_active_project", return_value=None), patch.object(
            self.executor, "execute", wraps=self.executor.execute
        ) as execute:
            verdict = self.verifier.check("verify", None)
        self.assertFalse(verdict.passed)
        self.assertIsNone(verdict.repository)
        self.assertEqual(execute.call_count, 0)

    def test_shell_metacharacters_remain_literal_arguments(self):
        literal = "; touch SHOULD_NOT_EXIST $(echo unsafe)"
        code = "import sys; print(sys.argv[1])"
        result = self.executor.execute(
            "run_command",
            {"argv": [sys.executable, "-c", code, literal], "cwd": str(self.root), "timeout": 2},
            {"task_id": "m4-argv", "workspace_dir": self.root, "require_project": True},
        )
        self.assertEqual(result.status, "success")
        self.assertIn(literal, result.output.details)
        self.assertFalse((self.root / "SHOULD_NOT_EXIST").exists())

    def test_single_flaky_retry_passes_and_records_both_attempts(self):
        marker = self.root / "first-attempt"
        self.python_project(
            "from pathlib import Path\n"
            f"marker = Path({str(marker)!r})\n"
            "def test_flaky_once():\n"
            "    if not marker.exists():\n"
            "        marker.write_text('failed once')\n"
            "        assert False, 'first attempt only'\n"
        )

        verdict = self.verifier.check("verify flaky fixture", self.root)

        self.assertTrue(verdict.passed, verdict.summary)
        self.assertTrue(verdict.retried)
        self.assertEqual(len(verdict.attempts), 2)
        self.assertEqual(verdict.attempts[0].commands[0].exit_status, 1)
        self.assertEqual(verdict.attempts[1].commands[0].exit_status, 0)

    def test_timeout_kills_process_group_and_is_recorded(self):
        if os.name != "posix":
            self.skipTest("Process-group termination test requires POSIX.")
        marker = self.root / "grandchild-survived"
        self.python_project(
            "import subprocess,sys,time\n"
            f"child = \"import pathlib,time; time.sleep(1.2); pathlib.Path({str(marker)!r}).write_text('alive')\"\n"
            "def test_hangs():\n"
            "    subprocess.Popen([sys.executable, '-c', child])\n"
            "    time.sleep(10)\n",
        )
        verifier = Verifier(self.executor, timeout_seconds=0.25)

        verdict = verifier.check("verify hanging test", self.root)
        time.sleep(1.5)

        self.assertFalse(verdict.passed)
        self.assertTrue(verdict.retried)
        self.assertTrue(all(command.timed_out for attempt in verdict.attempts for command in attempt.commands))
        self.assertFalse(marker.exists())

    def test_output_is_head_tail_truncated_and_nonzero_exit_is_failure(self):
        self.python_project(
            "print('output head marker')\n"
            "def test_output():\n"
            "    print('x' * 30000)\n"
            "    print('output tail marker')\n"
            "    assert False, 'failure retained'\n",
            config='\n[tool.pytest.ini_options]\naddopts = "-s"\n',
        )
        verdict = self.verifier.check("verify output fixture", self.root)
        final = verdict.attempts[-1].commands[0]
        self.assertFalse(verdict.passed)
        self.assertEqual(final.exit_status, 1)
        self.assertTrue(final.truncated)
        self.assertIn("output head marker", final.output)
        self.assertIn("output tail marker", final.output)
        self.assertIn("failure retained", final.output)


if __name__ == "__main__":
    unittest.main()
