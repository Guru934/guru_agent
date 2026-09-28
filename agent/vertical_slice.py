"""Small deterministic proof of the plan, act, and verify interfaces."""

import sys
import site
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent.events import emit
from agent.executor import ToolExecutor
from agent.tool_result import ToolResult
from memory.sqlite import get_active_project, validate_project_path


@dataclass(frozen=True)
class VerticalSlicePlan:
    goal: str
    steps: tuple[str, ...]


@dataclass(frozen=True)
class VerticalSliceResult:
    ok: bool
    summary: str
    repository: Optional[Path]
    plan: Optional[VerticalSlicePlan]
    action: Optional[ToolResult]
    verification: Optional[ToolResult]


class VerticalSliceRunner:
    """Run the single supported M3 task through existing coding tools."""

    _MARKER = "# TODO: implement add\n"
    _IMPLEMENTATION = "def add(a, b):\n    return a + b\n"

    def __init__(self, executor: ToolExecutor):
        self.executor = executor

    @staticmethod
    def _create_plan(goal: str) -> VerticalSlicePlan:
        words = goal.casefold()
        if not all(term in words for term in ("add", "function", "math.py", "test")):
            raise ValueError("The M3 vertical slice supports adding add(a, b) to math.py with a test.")
        return VerticalSlicePlan(
            goal=goal,
            steps=("replace_in_file math.py, then verify with pytest tests/test_math.py",),
        )

    @staticmethod
    def _failed_tool_result(summary: str) -> ToolResult:
        return ToolResult(False, summary, summary, False, None, False)

    def run(self, goal: str, repo_path: Optional[str | Path] = None) -> VerticalSliceResult:
        task_id = str(uuid.uuid4())
        emit("TASK_STARTED", task_id, {"description": goal})
        plan = None
        action = None
        verification = None
        repository = None
        try:
            plan = self._create_plan(goal)
            repository = (
                validate_project_path(str(repo_path))
                if repo_path is not None
                else get_active_project()
            )
            if repository is None:
                raise ValueError("No valid active project is selected for the vertical slice.")

            context = {
                "task_id": task_id,
                "workspace_dir": repository,
                "require_project": True,
            }
            action_execution = self.executor.execute(
                "replace_in_file",
                {"path": "math.py", "old": self._MARKER, "new": self._IMPLEMENTATION},
                context,
            )
            action = (
                action_execution.output
                if isinstance(action_execution.output, ToolResult)
                else self._failed_tool_result(str(action_execution.output))
            )
            if action_execution.status != "success" or not action.ok:
                raise RuntimeError(f"Action failed: {action.summary}")

            verify_execution = self.executor.execute(
                "run_command",
                {
                    "argv": [
                        sys.executable,
                        "-c",
                        "import os,site,sys; site.addsitedir(sys.argv[1]); "
                        "root=os.path.realpath(os.getcwd()); "
                        "sys.path[:]=[p for p in sys.path if os.path.realpath(p or root)!=root]; "
                        "import math,pytest; sys.path.insert(0,root); "
                        "raise SystemExit(pytest.main(sys.argv[2:]))",
                        site.getusersitepackages(),
                        "-q",
                        "tests/test_math.py",
                    ],
                    "cwd": str(repository),
                    "timeout": 30,
                },
                context,
            )
            verification = (
                verify_execution.output
                if isinstance(verify_execution.output, ToolResult)
                else self._failed_tool_result(str(verify_execution.output))
            )
            if verify_execution.status != "success" or not verification.ok:
                message = f"Verification failed: {verification.summary}"
                emit("TASK_FAILED", task_id, {"error": message})
                return VerticalSliceResult(False, message, repository, plan, action, verification)

            message = "Verified: the repository change passed pytest."
            emit("TASK_COMPLETED", task_id, {"result": message})
            return VerticalSliceResult(True, message, repository, plan, action, verification)
        except (OSError, RuntimeError, ValueError) as error:
            message = str(error)
            emit("TASK_FAILED", task_id, {"error": message})
            return VerticalSliceResult(False, message, repository, plan, action, verification)
