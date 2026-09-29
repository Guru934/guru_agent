import pytest
from unittest.mock import patch
from agent.coding_task import PlanStep, CodingTask, Budget, Status
from agent.verifier import Verdict

def test_valid_plan_step():
    step = PlanStep(description="Do X", acceptance_criteria="X is done")
    assert step.description == "Do X"
    assert step.acceptance_criteria == "X is done"

def test_default_budget_values():
    budget = Budget()
    assert budget.max_planned_steps == 7
    assert budget.max_total_action_steps == 20
    assert budget.max_attempts_per_step == 3
    assert budget.max_wall_time == 1200
    assert budget.max_tokens is None
    assert budget.current_action_steps == 0
    assert budget.current_tokens == 0

def test_budget_validation():
    # Test rejection of negative budget values
    with pytest.raises(ValueError):
        Budget(max_planned_steps=-1)
    with pytest.raises(ValueError):
        Budget(max_total_action_steps=-5)
    with pytest.raises(ValueError):
        Budget(max_attempts_per_step=-1)
    with pytest.raises(ValueError):
        Budget(max_wall_time=-10)
    with pytest.raises(ValueError):
        Budget(max_tokens=-100)

def test_valid_coding_task():
    task = CodingTask(
        task_id="task-123",
        goal="Implement feature",
        canonical_repository="/repo"
    )
    assert task.task_id == "task-123"
    assert task.goal == "Implement feature"
    assert task.canonical_repository == "/repo"
    assert task.status == Status.PLANNING
    assert len(task.validated_plan) == 0
    assert task.current_step == 0

def test_max_7_plan_steps_allowed():
    plan = [PlanStep(f"D{i}", f"A{i}") for i in range(7)]
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r", validated_plan=plan)
    assert len(task.validated_plan) == 7

def test_rejection_of_more_than_7_steps():
    plan = [PlanStep(f"D{i}", f"A{i}") for i in range(8)]
    with pytest.raises(ValueError, match="Plan cannot exceed 7 steps"):
        CodingTask(task_id="t1", goal="g", canonical_repository="/r", validated_plan=plan)

def test_attempt_counter_validation():
    with pytest.raises(ValueError, match="Attempts cannot be negative"):
        CodingTask(task_id="t1", goal="g", canonical_repository="/r", per_step_attempts={0: -1})

    with pytest.raises(ValueError, match="Step index cannot be negative"):
        CodingTask(task_id="t1", goal="g", canonical_repository="/r", per_step_attempts={-1: 0})

    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r", per_step_attempts={0: 2, 1: 0})
    assert task.per_step_attempts[0] == 2
    assert task.per_step_attempts[1] == 0

def test_valid_status_values():
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r", status=Status.DONE)
    assert task.status == Status.DONE

    # string conversions supported by the dataclass __post_init__ logic (now handled in set_status)
    task2 = CodingTask(task_id="t1", goal="g", canonical_repository="/r", status="BLOCKED")
    assert task2.status == Status.BLOCKED

def test_invalid_status_rejection():
    with pytest.raises(ValueError, match="Invalid status"):
        CodingTask(task_id="t1", goal="g", canonical_repository="/r", status="NOT_A_STATUS")

    with pytest.raises(ValueError, match="Invalid status"):
        CodingTask(task_id="t1", goal="g", canonical_repository="/r", status=123)

def test_current_step_validation():
    # Without plan
    with pytest.raises(ValueError, match="Current step cannot be negative"):
        CodingTask(task_id="t1", goal="g", canonical_repository="/r", current_step=-1)

    # Valid step with setup
    plan = [PlanStep(f"D{i}", f"A{i}") for i in range(5)]
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r", validated_plan=plan, current_step=3)
    assert task.current_step == 3

def test_artifact_storage():
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r", artifacts=["artifact1", {"key": "val"}])
    assert len(task.artifacts) == 2
    assert task.artifacts[0] == "artifact1"
    assert task.artifacts[1] == {"key": "val"}

def test_verification_result_storage():
    v1 = Verdict(passed=True, step="S1", repository=None, attempts=(), retried=False, summary="")
    v2 = Verdict(passed=False, step="S2", repository=None, attempts=(), retried=False, summary="")
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r", verification_results=[v1, v2])
    assert len(task.verification_results) == 2
    assert task.verification_results[0].passed is True
    assert task.verification_results[1].passed is False

# --- Explicit post-construction mutation tests ---

def test_cannot_add_8th_plan_step():
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r")
    plan = [PlanStep(f"D{i}", f"A{i}") for i in range(7)]
    task.set_plan(plan)

    plan8 = [PlanStep(f"D{i}", f"A{i}") for i in range(8)]
    with pytest.raises(ValueError, match="Plan cannot exceed 7 steps"):
        task.set_plan(plan8)

    # Test tuple restriction prevents direct modification
    with pytest.raises(AttributeError):
        task.validated_plan.append(PlanStep("x", "y"))

def test_cannot_insert_negative_attempt():
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r")
    # Mutating returned dict explicitly does not change task
    dict_copy = task.per_step_attempts
    dict_copy[0] = -5
    assert 0 not in task.per_step_attempts

    # Also ensures that attempts exceeding limit fail
    task.record_attempt(0)
    task.record_attempt(0)
    task.record_attempt(0)
    with pytest.raises(ValueError, match="Attempts for step 0 exceed maximum"):
        task.record_attempt(0)

def test_cannot_insert_invalid_step_index():
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r")
    with pytest.raises(ValueError, match="Step index cannot be negative"):
        task.record_attempt(-1)

def test_cannot_set_invalid_status():
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r")
    with pytest.raises(ValueError, match="Invalid status"):
        task.set_status("INVALID")

def test_cannot_set_current_step_to_invalid_value():
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r")
    # Before plan exists, cannot set to >0
    with pytest.raises(ValueError, match="Current step must be 0 before a plan exists"):
        task.set_current_step(1)

    # Setting an existing plan
    task.set_plan([PlanStep("d", "a") for _ in range(3)])

    # Negative disallowed
    with pytest.raises(ValueError, match="Current step cannot be negative"):
        task.set_current_step(-1)

    # N disallowed
    with pytest.raises(ValueError, match="Current step 3 is out of bounds"):
        task.set_current_step(3)

    # N+1 disallowed
    with pytest.raises(ValueError, match="Current step 4 is out of bounds"):
        task.set_current_step(4)

def test_cannot_make_action_counter_negative():
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r")
    with pytest.raises(ValueError, match="cannot make action counter negative"):
        task.budget.increment_action_steps(-1)

def test_cannot_make_token_counter_negative():
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r")
    with pytest.raises(ValueError, match="cannot make token counter negative"):
        task.budget.record_token_usage(-1)

def test_valid_controlled_mutation_succeeds():
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r")

    task.set_status(Status.ACTING)
    assert task.status == Status.ACTING

    plan3 = [PlanStep(f"d{i}", f"a{i}") for i in range(3)]
    task.set_plan(plan3)

    task.set_current_step(2)
    assert task.current_step == 2

def test_artifacts_remain_independent_per_task():
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r")
    task.add_artifact("item1")
    # Mutating returned tuple should fail
    with pytest.raises(AttributeError):
        task.artifacts.append("item2")
    assert task.artifacts == ("item1",)

def test_verification_results_remain_independent_per_task():
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r")
    task.add_verification_result(Verdict(passed=True, step="", repository=None, attempts=(), retried=False, summary=""))
    # Mutating returned tuple should fail
    with pytest.raises(AttributeError):
        task.verification_results.append(Verdict(passed=False, step="", repository=None, attempts=(), retried=False, summary=""))
    assert len(task.verification_results) == 1

def test_set_plan_resets_current_step():
    task = CodingTask(task_id="t1", goal="g", canonical_repository="/r")
    task.set_plan([PlanStep(f"d{i}", f"a{i}") for i in range(5)])

    # move ahead
    task.set_current_step(3)
    assert task.current_step == 3

    # replace plan with a different size
    task.set_plan([PlanStep(f"x{i}", f"y{i}") for i in range(2)])
    assert task.current_step == 0

# --- Exhaustion Tests ---

def test_budget_not_exhausted_initially():
    budget = Budget()
    is_exh, reason = budget.is_exhausted()
    assert is_exh is False
    assert reason == ""

def test_budget_action_limit_exhaustion():
    budget = Budget(max_total_action_steps=5)
    budget.increment_action_steps(4)
    assert budget.is_exhausted() == (False, "")

    # Exceeding limit should record cleanly without raising
    budget.increment_action_steps(2)
    is_exh, reason = budget.is_exhausted()
    assert is_exh is True
    assert reason == "Action limit reached"

def test_budget_token_limit_exhaustion():
    budget = Budget(max_tokens=100)
    budget.record_token_usage(90)
    assert budget.is_exhausted() == (False, "")

    # Exceeding limit should record cleanly without raising
    budget.record_token_usage(20)
    is_exh, reason = budget.is_exhausted()
    assert is_exh is True
    assert reason == "Token limit reached"

@patch("time.monotonic")
def test_budget_wall_time_exhaustion(mock_time):
    # initialize with known time
    mock_time.return_value = 100.0
    budget = Budget(max_wall_time=300)

    mock_time.return_value = 200.0
    assert budget.is_exhausted() == (False, "")

    mock_time.return_value = 450.0  # 350 seconds elapsed, exceeds max of 300
    is_exh, reason = budget.is_exhausted()
    assert is_exh is True
    assert reason == "Wall time limit reached"

@patch("time.monotonic")
def test_budget_reset_timer(mock_time):
    mock_time.return_value = 0.0
    budget = Budget(max_wall_time=300)

    mock_time.return_value = 350.0
    assert budget.is_exhausted()[0] is True

    # Restart the timer at 350
    budget.reset_timer()
    assert budget.is_exhausted() == (False, "")

