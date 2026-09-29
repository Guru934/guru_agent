from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence, Iterator, Any

from agent.coding_task import PlanStep
from agent.verifier import Verdict
from agent.tool_result import ToolResult

@dataclass(frozen=True)
class RepoContext:
    root: Path
    languages: tuple[str, ...]
    test_commands: tuple[tuple[str, ...], ...]

@dataclass(frozen=True)
class Impossible:
    reason: str

@dataclass(frozen=True)
class ActionResult:
    ok: bool
    summary: str
    changed: bool
    artifact: str | None
    truncated: bool

class Plan:
    """
    Immutable validated planner output.

    Enforces the M5 invariant: at most 7 steps.
    Use a defensive copy so callers cannot mutate the stored plan.
    Construction with > 7 steps raises ValueError.
    """
    MAX_STEPS: int = 7

    def __init__(self, steps: Sequence[PlanStep]):
        steps_copy = tuple(steps)
        if len(steps_copy) > self.MAX_STEPS:
            raise ValueError(f"Plan cannot exceed {self.MAX_STEPS} steps")
        self._steps = steps_copy

    def __len__(self) -> int:
        return len(self._steps)

    def __iter__(self) -> Iterator[PlanStep]:
        return iter(self._steps)

    @property
    def steps(self) -> tuple[PlanStep, ...]:
        return self._steps

class CodingTools(Protocol):
    def list_files(self, glob: str, max: int = 200) -> ToolResult: ...
    def read_file(self, path: str, start_line: int | None = None, end_line: int | None = None) -> ToolResult: ...
    def search(self, query: str, path: str | None = None, glob: str | None = None) -> ToolResult: ...
    def replace_in_file(self, path: str, old: str, new: str) -> ToolResult: ...
    def git_status(self) -> ToolResult: ...
    def git_diff(self) -> ToolResult: ...
    def run_command(self, argv: list[str], cwd: str, timeout: int) -> ToolResult: ...

class Planner(Protocol):
    def plan(self, goal: str, repo_context: RepoContext) -> Plan | Impossible: ...

class Actor(Protocol):
    def act(self, step: PlanStep, repo: RepoContext, tools: CodingTools) -> ActionResult: ...

class Reflector(Protocol):
    def reflect(self, step: PlanStep, attempt: int, verdict: Verdict) -> PlanStep | Impossible: ...

class FakePlanner:
    def __init__(self, script: Sequence[Any]):
        self._script = list(script)

    def plan(self, goal: str, repo_context: RepoContext) -> Any:
        if not self._script:
            raise RuntimeError("FakePlanner exhausted")
        return self._script.pop(0)

class FakeActor:
    def __init__(self, script: Sequence[Any], delay_fn=None):
        self._script = list(script)
        self._delay_fn = delay_fn

    def act(self, step: PlanStep, repo: RepoContext, tools: CodingTools) -> Any:
        if self._delay_fn is not None:
            self._delay_fn()
        if not self._script:
            raise RuntimeError("FakeActor exhausted")
        return self._script.pop(0)

class FakeReflector:
    def __init__(self, script: Sequence[Any]):
        self._script = list(script)

    def reflect(self, step: PlanStep, attempt: int, verdict: Verdict) -> Any:
        if not self._script:
            raise RuntimeError("FakeReflector exhausted")
        return self._script.pop(0)
