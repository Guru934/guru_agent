import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.executor import ToolExecutor
from agent.tool_registry import registry
from config import APP_DIR, DB_PATH, USER_STATE_DIR
from tools.workspace import resolve_workspace_path


class CodingToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="guru-m2-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "m2@example.test"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "M2 Test"], check=True)

        from agent.policy import engine as policy_engine

        self.policy = policy_engine
        self.original_safe_mode = self.policy.safe_mode
        self.original_audit = self.policy.audit_file
        self.policy.safe_mode = False
        self.policy.audit_file = Path(self.temp.name) / "security_audit.log"
        self.addCleanup(setattr, self.policy, "safe_mode", self.original_safe_mode)
        self.addCleanup(setattr, self.policy, "audit_file", self.original_audit)
        self.executor = ToolExecutor(registry)
        self.context = {
            "task_id": "m2-test",
            "workspace_dir": self.root,
            "require_project": True,
        }

    def execute(self, name, **arguments):
        return self.executor.execute(name, arguments, self.context)

    def test_required_coding_tools_are_registered(self):
        expected = {
            "list_files", "read_file", "search", "replace_in_file",
            "git_status", "git_diff", "run_command",
        }
        self.assertTrue(expected.issubset({spec.name for spec in registry.get_all_specs()}))

    def test_list_files_returns_expected_files_and_enforces_limit(self):
        for name in ("a.py", "b.py", "c.py", "d.py"):
            (self.root / name).write_text(name, encoding="utf-8")

        result = self.execute("list_files", glob="*.py", **{"max": 2})
        self.assertTrue(result.output.ok)
        self.assertEqual(result.output.details.splitlines(), ["a.py", "b.py"])
        self.assertTrue(result.output.truncated)

    def test_list_files_caps_requested_max_at_200(self):
        for index in range(205):
            (self.root / f"file-{index:03}.txt").write_text("x", encoding="utf-8")
        result = self.execute("list_files", glob="*.txt", **{"max": 201})
        self.assertTrue(result.output.ok)
        self.assertEqual(len(result.output.details.splitlines()), 200)
        self.assertTrue(result.output.truncated)

    def test_list_files_omits_paths_marked_protected(self):
        (self.root / "visible.py").write_text("visible", encoding="utf-8")
        (self.root / "protected.py").write_text("private", encoding="utf-8")
        with patch("tools.coding._protected_file", side_effect=lambda path, root: path.name == "protected.py"):
            result = self.execute("list_files", glob="*.py")
        self.assertIn("visible.py", result.output.details)
        self.assertNotIn("protected.py", result.output.details)

    def test_list_files_does_not_expose_protected_hard_link(self):
        protected_alias = self.root / "source_alias.py"
        try:
            os.link(APP_DIR / "config.py", protected_alias)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Filesystem cannot create protected source hard link: {error}")

        result = self.execute("list_files", glob="*.py")
        self.assertTrue(result.output.ok)
        self.assertNotIn("source_alias.py", result.output.details)

    def test_ranged_read_file_works(self):
        (self.root / "lines.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
        result = self.execute("read_file", path="lines.txt", start_line=2, end_line=3)
        self.assertTrue(result.output.ok)
        self.assertEqual(result.output.details, "two\nthree\n")

    def test_read_file_rejects_invalid_line_ranges(self):
        (self.root / "lines.txt").write_text("one\ntwo\n", encoding="utf-8")
        for args in (
            {"start_line": 0},
            {"start_line": 2, "end_line": 1},
            {"start_line": 3},
            {"end_line": 3},
        ):
            with self.subTest(args=args):
                result = self.execute("read_file", path="lines.txt", **args)
                self.assertFalse(result.output.ok)
                self.assertIn("line", result.output.summary.lower())

    def test_search_finds_matches_and_honors_filters(self):
        (self.root / "one.py").write_text("needle here\n", encoding="utf-8")
        (self.root / "two.txt").write_text("needle elsewhere\n", encoding="utf-8")
        result = self.execute("search", query="needle", glob="*.py")
        self.assertTrue(result.output.ok)
        self.assertIn("one.py:1:needle here", result.output.details)
        self.assertNotIn("two.txt", result.output.details)

    def test_search_cannot_escape_project_scope(self):
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("secretword\n", encoding="utf-8")
        result = self.execute("search", query="secretword", path="../outside.txt")
        self.assertEqual(result.status, "denied")

    def test_replace_in_file_changes_exactly_one_match(self):
        target = self.root / "replace.txt"
        target.write_text("before\nafter\n", encoding="utf-8")
        result = self.execute("replace_in_file", path="replace.txt", old="before", new="changed")
        self.assertTrue(result.output.ok)
        self.assertTrue(result.output.changed)
        self.assertEqual(target.read_text(encoding="utf-8"), "changed\nafter\n")

    def test_replace_in_file_rejects_zero_matches(self):
        (self.root / "replace.txt").write_text("before\n", encoding="utf-8")
        result = self.execute("replace_in_file", path="replace.txt", old="missing", new="changed")
        self.assertFalse(result.output.ok)
        self.assertIn("zero", result.output.summary.lower())

    def test_replace_in_file_rejects_multiple_matches(self):
        (self.root / "replace.txt").write_text("same\nsame\n", encoding="utf-8")
        result = self.execute("replace_in_file", path="replace.txt", old="same", new="changed")
        self.assertFalse(result.output.ok)
        self.assertIn("multiple", result.output.summary)

    def test_replace_in_file_counts_overlapping_matches(self):
        (self.root / "replace.txt").write_text("aaa", encoding="utf-8")
        result = self.execute("replace_in_file", path="replace.txt", old="aa", new="x")
        self.assertFalse(result.output.ok)
        self.assertIn("multiple", result.output.summary)

    def test_replace_does_not_leave_stale_read_content(self):
        (self.root / "replace.txt").write_text("old", encoding="utf-8")
        first = self.execute("read_file", path="replace.txt")
        self.assertEqual(first.output.details, "old")
        self.execute("replace_in_file", path="replace.txt", old="old", new="new")
        second = self.execute("read_file", path="replace.txt")
        self.assertEqual(second.output.details, "new")

    def test_git_status_reports_selected_repository(self):
        (self.root / "untracked.txt").write_text("pending", encoding="utf-8")
        result = self.execute("git_status")
        self.assertTrue(result.output.ok)
        status = json.loads(result.output.artifact)
        self.assertEqual(status["repository"], str(self.root.resolve()))
        self.assertTrue(any("untracked.txt" in entry for entry in status["entries"]))

    def test_git_diff_reports_changes_from_selected_repository(self):
        tracked = self.root / "tracked.txt"
        tracked.write_text("original\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "tracked.txt"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "baseline"], check=True)
        tracked.write_text("updated\n", encoding="utf-8")
        result = self.execute("git_diff")
        self.assertTrue(result.output.ok)
        self.assertIn("tracked.txt", result.output.details)
        self.assertIn("-original", result.output.details)
        self.assertIn("+updated", result.output.details)

    def test_git_diff_output_is_bounded_and_truncated(self):
        tracked = self.root / "large.txt"
        tracked.write_text("old\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "large.txt"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "baseline"], check=True)
        tracked.write_text("line\n" * 10_000, encoding="utf-8")
        result = self.execute("git_diff")
        self.assertTrue(result.output.ok)
        self.assertTrue(result.output.truncated)
        self.assertIn("Output truncated", result.output.details)
        self.assertLess(len(result.output.details), 14_000)

    def test_run_command_executes_argv_and_uses_requested_project_cwd(self):
        code = "import os,sys; print(os.getcwd()); print(repr(sys.argv[1]))"
        metacharacters = "semi; $HOME $(echo unsafe)"
        result = self.execute(
            "run_command", argv=[sys.executable, "-c", code, metacharacters], cwd=".", timeout=5
        )
        self.assertTrue(result.output.ok)
        self.assertIn(str(self.root.resolve()), result.output.details)
        self.assertIn(repr(metacharacters), result.output.details)

    def test_run_command_rejects_cwd_outside_project(self):
        result = self.execute(
            "run_command", argv=[sys.executable, "-c", "print('no')"],
            cwd="../outside", timeout=5,
        )
        self.assertEqual(result.status, "denied")

    def test_run_command_preserves_nonzero_exit_output(self):
        result = self.execute(
            "run_command", argv=[sys.executable, "-c", "import sys; print('failure'); sys.exit(7)"],
            cwd=".", timeout=5,
        )
        self.assertFalse(result.output.ok)
        self.assertIn("7", result.output.summary)
        self.assertIn("failure", result.output.details)

    def test_run_command_times_out_and_terminates_process_group(self):
        marker = Path(self.temp.name) / "grandchild-survived"
        child = "import pathlib,time; time.sleep(.8); pathlib.Path(%r).write_text('survived')" % str(marker)
        parent = (
            "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',sys.argv[1]]); time.sleep(10)"
        )
        result = self.execute(
            "run_command", argv=[sys.executable, "-c", parent, child], cwd=".", timeout=0.2
        )
        self.assertFalse(result.output.ok)
        self.assertIn("timed out", result.output.summary.lower())
        time.sleep(1.0)
        self.assertFalse(marker.exists(), "child process survived timeout process-group termination")

    def test_run_command_output_is_bounded_and_keeps_head_and_tail(self):
        result = self.execute(
            "run_command",
            argv=[sys.executable, "-c", "print('head'); print('x'*100000); print('tail')"],
            cwd=".", timeout=5,
        )
        self.assertTrue(result.output.ok)
        self.assertTrue(result.output.truncated)
        self.assertIn("head", result.output.details)
        self.assertIn("tail", result.output.details)
        self.assertLess(len(result.output.details), 14000)

    def test_coding_tools_remain_subject_to_protected_path_policy(self):
        for protected in (APP_DIR / "config.py", DB_PATH, USER_STATE_DIR / "security_audit.log"):
            with self.subTest(protected=protected):
                decision = self.policy.evaluate(
                    "replace_in_file",
                    {"path": str(protected), "old": "x", "new": "y"},
                    {**self.context, "workspace_dir": self.root},
                )
                self.assertFalse(decision.allowed)
                self.assertIn("protected", decision.reason.lower())

    def test_coding_write_requires_existing_approval_policy(self):
        self.policy.safe_mode = True
        decision = self.policy.evaluate(
            "replace_in_file", {"path": "file.txt", "old": "a", "new": "b"}, self.context
        )
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_approval)


if __name__ == "__main__":
    unittest.main()
