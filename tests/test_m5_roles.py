import ast
import pytest
from pathlib import Path
from agent.roles import (
    RepoContext,
    Impossible,
    ActionResult,
    Plan,
    FakePlanner,
    FakeActor,
    FakeReflector,
)
from agent.coding_task import PlanStep
from agent.verifier import Verdict


class TestRepoContext:
    def test_repo_context_creation(self):
        ctx = RepoContext(
            root=Path("/repo"),
            languages=("python", "typescript"),
            test_commands=(("pytest",), ("npm", "test")),
        )
        assert ctx.root == Path("/repo")
        assert ctx.languages == ("python", "typescript")
        assert ctx.test_commands == (("pytest",), ("npm", "test"))

    def test_repo_context_frozen(self):
        ctx = RepoContext(root=Path("/repo"), languages=(), test_commands=())
        with pytest.raises(AttributeError):
            ctx.root = Path("/other")


class TestImpossible:
    def test_impossible_creation(self):
        imp = Impossible(reason="cannot complete")
        assert imp.reason == "cannot complete"

    def test_impossible_frozen(self):
        imp = Impossible(reason="test")
        with pytest.raises(AttributeError):
            imp.reason = "other"


class TestActionResult:
    def test_action_result_creation(self):
        res = ActionResult(
            ok=True,
            summary="Done",
            changed=True,
            artifact="file.py",
            truncated=False,
        )
        assert res.ok is True
        assert res.summary == "Done"
        assert res.changed is True
        assert res.artifact == "file.py"
        assert res.truncated is False

    def test_action_result_frozen(self):
        res = ActionResult(ok=True, summary="", changed=False, artifact=None, truncated=False)
        with pytest.raises(AttributeError):
            res.ok = False


class TestPlan:
    def test_valid_plan_with_7_steps(self):
        steps = [PlanStep(f"D{i}", f"A{i}") for i in range(7)]
        plan = Plan(steps)
        assert len(plan) == 7
        assert plan.steps == tuple(steps)

    def test_valid_plan_with_zero_steps(self):
        plan = Plan([])
        assert len(plan) == 0
        assert plan.steps == ()

    def test_plan_rejects_8_steps(self):
        steps = [PlanStep(f"D{i}", f"A{i}") for i in range(8)]
        with pytest.raises(ValueError, match="Plan cannot exceed 7 steps"):
            Plan(steps)

    def test_plan_defensive_copy(self):
        steps = [PlanStep("D1", "A1"), PlanStep("D2", "A2")]
        plan = Plan(steps)
        steps.append(PlanStep("D3", "A3"))
        assert len(plan) == 2
        assert plan.steps == (steps[0], steps[1])

    def test_plan_iteration(self):
        steps = [PlanStep(f"D{i}", f"A{i}") for i in range(3)]
        plan = Plan(steps)
        iterated = list(plan)
        assert iterated == steps

    def test_plan_len(self):
        steps = [PlanStep(f"D{i}", f"A{i}") for i in range(5)]
        plan = Plan(steps)
        assert len(plan) == 5


class TestFakePlanner:
    def test_valid_plan_script(self):
        plan = Plan([PlanStep("D1", "A1"), PlanStep("D2", "A2")])
        fake = FakePlanner([plan])
        result = fake.plan("goal", RepoContext(Path("/"), (), ()))
        assert result is plan

    def test_zero_step_plan_impossible(self):
        imp = Impossible(reason="nothing to do")
        fake = FakePlanner([imp])
        result = fake.plan("goal", RepoContext(Path("/"), (), ()))
        assert result is imp
        assert isinstance(result, Impossible)

    def test_malformed_output_string(self):
        fake = FakePlanner(["just a string"])
        result = fake.plan("goal", RepoContext(Path("/"), (), ()))
        assert result == "just a string"

    def test_malformed_output_dict(self):
        fake = FakePlanner([{"steps": []}])
        result = fake.plan("goal", RepoContext(Path("/"), (), ()))
        assert result == {"steps": []}

    def test_malformed_output_none(self):
        fake = FakePlanner([None])
        result = fake.plan("goal", RepoContext(Path("/"), (), ()))
        assert result is None

    def test_more_than_7_steps_for_boundary_test(self):
        steps = [PlanStep(f"D{i}", f"A{i}") for i in range(8)]
        fake = FakePlanner([steps])
        result = fake.plan("goal", RepoContext(Path("/"), (), ()))
        assert result == steps
        assert len(result) == 8

    def test_exhaustion_raises_runtime_error(self):
        fake = FakePlanner([Plan([])])
        fake.plan("goal", RepoContext(Path("/"), (), ()))
        with pytest.raises(RuntimeError, match="FakePlanner exhausted"):
            fake.plan("goal", RepoContext(Path("/"), (), ()))


class TestFakeActor:
    def test_repeated_identical_failure(self):
        res = ActionResult(ok=False, summary="fail", changed=False, artifact=None, truncated=False)
        fake = FakeActor([res, res, res])
        ctx = RepoContext(Path("/"), (), ())
        step = PlanStep("D1", "A1")
        for _ in range(3):
            result = fake.act(step, ctx, None)
            assert result is res
            assert result.ok is False

    def test_failure_then_success(self):
        fail = ActionResult(ok=False, summary="fail", changed=False, artifact=None, truncated=False)
        success = ActionResult(ok=True, summary="ok", changed=True, artifact="file.py", truncated=False)
        fake = FakeActor([fail, success])
        ctx = RepoContext(Path("/"), (), ())
        step = PlanStep("D1", "A1")
        assert fake.act(step, ctx, None) is fail
        assert fake.act(step, ctx, None) is success

    def test_ok_then_externally_failing_verdict(self):
        res = ActionResult(ok=True, summary="done", changed=True, artifact="file.py", truncated=False)
        fake = FakeActor([res])
        ctx = RepoContext(Path("/"), (), ())
        step = PlanStep("D1", "A1")
        result = fake.act(step, ctx, None)
        assert result is res
        assert result.ok is True
        assert result.changed is True

    def test_malformed_output_string(self):
        fake = FakeActor(["not an action result"])
        ctx = RepoContext(Path("/"), (), ())
        step = PlanStep("D1", "A1")
        result = fake.act(step, ctx, None)
        assert result == "not an action result"

    def test_injectable_delay_via_callable(self):
        calls = []

        def delay_fn():
            calls.append("delayed")

        fake = FakeActor([ActionResult(True, "ok", True, "x", False)], delay_fn=delay_fn)
        ctx = RepoContext(Path("/"), (), ())
        step = PlanStep("D1", "A1")
        fake.act(step, ctx, None)
        assert calls == ["delayed"]

    def test_exhaustion_raises_runtime_error(self):
        fake = FakeActor([ActionResult(True, "ok", True, "x", False)])
        ctx = RepoContext(Path("/"), (), ())
        step = PlanStep("D1", "A1")
        fake.act(step, ctx, None)
        with pytest.raises(RuntimeError, match="FakeActor exhausted"):
            fake.act(step, ctx, None)


class TestFakeReflector:
    def test_revised_plan_step(self):
        step1 = PlanStep("D1", "A1")
        step2 = PlanStep("D1 revised", "A1 revised")
        fake = FakeReflector([step2])
        verdict = Verdict(passed=False, step="S1", repository=None, attempts=(), retried=False, summary="")
        result = fake.reflect(step1, 1, verdict)
        assert result is step2
        assert result.description == "D1 revised"

    def test_same_step_twice(self):
        step = PlanStep("D1", "A1")
        fake = FakeReflector([step, step])
        verdict = Verdict(passed=False, step="S1", repository=None, attempts=(), retried=False, summary="")
        assert fake.reflect(step, 1, verdict) is step
        assert fake.reflect(step, 2, verdict) is step

    def test_impossible_with_reason(self):
        imp = Impossible(reason="give up")
        fake = FakeReflector([imp])
        verdict = Verdict(passed=False, step="S1", repository=None, attempts=(), retried=False, summary="")
        result = fake.reflect(PlanStep("D1", "A1"), 1, verdict)
        assert result is imp
        assert isinstance(result, Impossible)

    def test_malformed_output(self):
        fake = FakeReflector(["not a step"])
        verdict = Verdict(passed=False, step="S1", repository=None, attempts=(), retried=False, summary="")
        result = fake.reflect(PlanStep("D1", "A1"), 1, verdict)
        assert result == "not a step"

    def test_exhaustion_raises_runtime_error(self):
        fake = FakeReflector([PlanStep("D1", "A1")])
        verdict = Verdict(passed=False, step="S1", repository=None, attempts=(), retried=False, summary="")
        fake.reflect(PlanStep("D1", "A1"), 1, verdict)
        with pytest.raises(RuntimeError, match="FakeReflector exhausted"):
            fake.reflect(PlanStep("D1", "A1"), 1, verdict)


# --- Boundary Invariant Guard (AST-based) ---

ALLOWLIST = {
    "agent/executor.py",
    "agent/policy.py",
    "agent/verifier.py",
}

FORBIDDEN_FUNCTIONS = {
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "os.system",
    "os.popen",
    "open",
    "Path.read_text",
    "Path.write_text",
    "Path.read_bytes",
    "Path.write_bytes",
}


def _get_call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        parts = []
        cur = node.func
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _check_forbidden_calls(filepath: Path, tree: ast.AST) -> list[tuple[int, str]]:
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = _get_call_name(node)
            if call_name and call_name in FORBIDDEN_FUNCTIONS:
                violations.append((node.lineno, call_name))
    return violations


def test_architecture_boundary_guard():
    """
    Scan agent/ modules for direct use of forbidden operations.
    Only modules in ALLOWLIST may use subprocess, os.system, os.popen,
    open(), Path.read_text, Path.write_text, Path.read_bytes, Path.write_bytes.
    """
    agent_dir = Path(__file__).parent.parent / "agent"
    violations = []

    for py_file in agent_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
        rel_path = py_file.relative_to(agent_dir.parent).as_posix()
        if rel_path in ALLOWLIST:
            continue

        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
        file_violations = _check_forbidden_calls(py_file, tree)

        for lineno, call_name in file_violations:
            violations.append(f"{rel_path}:{lineno}: forbidden call to {call_name}")

    if violations:
        pytest.fail(
            "Architecture boundary violations detected:\n" + "\n".join(violations)
            + "\n\nFix the violation by routing through ToolExecutor. Do NOT add to"
            + " ALLOWLIST unless this is a low-level infrastructure module."
        )


def test_allowlist_is_minimal():
    """
    Ensure the ALLOWLIST contains exactly the three low-level infrastructure
    modules and nothing else. This locks the boundary against future widening.
    """
    expected = {
        "agent/executor.py",
        "agent/policy.py",
        "agent/verifier.py",
    }
    assert ALLOWLIST == expected, (
        f"ALLOWLIST must be exactly {expected}, got {ALLOWLIST}. "
        f"Do not add modules; fix violations by routing through ToolExecutor."
    )