from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Any

class Status(Enum):
    PLANNING = "PLANNING"
    ACTING = "ACTING"
    VERIFYING = "VERIFYING"
    REFLECTING = "REFLECTING"
    RETRYING = "RETRYING"
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"

@dataclass
class PlanStep:
    description: str
    acceptance_criteria: str

@dataclass
class Budget:
    max_planned_steps: int = 7
    max_total_action_steps: int = 20
    max_attempts_per_step: int = 3
    max_wall_time: int = 1200 # seconds
    max_tokens: Optional[int] = None
    
    _current_action_steps: int = field(default=0, init=False)
    _current_tokens: int = field(default=0, init=False)
    
    def __post_init__(self):
        if self.max_planned_steps < 0:
            raise ValueError("max_planned_steps must be non-negative")
        if self.max_total_action_steps < 0:
            raise ValueError("max_total_action_steps must be non-negative")
        if self.max_attempts_per_step < 0:
            raise ValueError("max_attempts_per_step must be non-negative")
        if self.max_wall_time < 0:
            raise ValueError("max_wall_time must be non-negative")
        if self.max_tokens is not None and self.max_tokens < 0:
            raise ValueError("max_tokens must be non-negative")

    @property
    def current_action_steps(self) -> int:
        return self._current_action_steps
        
    @property
    def current_tokens(self) -> int:
        return self._current_tokens
        
    def increment_action_steps(self, count: int = 1):
        if count < 0:
            raise ValueError("cannot make action counter negative")
        if self._current_action_steps + count > self.max_total_action_steps:
            raise ValueError("cannot exceed max_total_action_steps")
        self._current_action_steps += count

    def record_token_usage(self, amount: int):
        if amount < 0:
            raise ValueError("cannot make token counter negative")
        if self.max_tokens is not None and self._current_tokens + amount > self.max_tokens:
            raise ValueError("cannot exceed configured token budget")
        self._current_tokens += amount


class CodingTask:
    def __init__(self, task_id: str, goal: str, canonical_repository: str,
                 validated_plan: Optional[List[PlanStep]] = None,
                 current_step: int = 0,
                 per_step_attempts: Optional[Dict[int, int]] = None,
                 status: Any = Status.PLANNING,
                 artifacts: Optional[List[Any]] = None,
                 verification_results: Optional[List[Any]] = None,
                 budget: Optional[Budget] = None):
        
        self._task_id = task_id
        self._goal = goal
        self._canonical_repository = canonical_repository
        self._budget = budget or Budget()
        
        self._validated_plan: List[PlanStep] = []
        if validated_plan is not None:
            self.set_plan(validated_plan)
            
        self._current_step = 0
        self.set_current_step(current_step)
        
        self._per_step_attempts: Dict[int, int] = {}
        if per_step_attempts is not None:
            for idx, attempts in per_step_attempts.items():
                if idx < 0:
                    raise ValueError("Step index cannot be negative")
                if attempts < 0:
                    raise ValueError("Attempts cannot be negative")
                if attempts > self._budget.max_attempts_per_step:
                    raise ValueError("Attempts exceed maximum")
                self._per_step_attempts[idx] = attempts
                
        self._status = Status.PLANNING
        self.set_status(status)
        
        self._artifacts: List[Any] = list(artifacts) if artifacts else []
        self._verification_results: List[Any] = list(verification_results) if verification_results else []

    @property
    def task_id(self) -> str:
        return self._task_id

    @property
    def goal(self) -> str:
        return self._goal

    @property
    def canonical_repository(self) -> str:
        return self._canonical_repository

    @property
    def budget(self) -> Budget:
        return self._budget

    @property
    def validated_plan(self) -> tuple:
        return tuple(self._validated_plan)

    @property
    def per_step_attempts(self) -> dict:
        return dict(self._per_step_attempts)

    @property
    def current_step(self) -> int:
        return self._current_step

    @property
    def status(self) -> Status:
        return self._status

    @property
    def artifacts(self) -> tuple:
        return tuple(self._artifacts)

    @property
    def verification_results(self) -> tuple:
        return tuple(self._verification_results)

    def set_plan(self, steps: List[PlanStep]):
        if len(steps) > self._budget.max_planned_steps:
            raise ValueError(f"Plan cannot exceed {self._budget.max_planned_steps} steps")
        self._validated_plan = list(steps)
        self._current_step = 0

    def set_current_step(self, step_idx: int):
        if step_idx < 0:
            raise ValueError("Current step cannot be negative")
        
        n_steps = len(self._validated_plan)
        if n_steps == 0:
            if step_idx != 0:
                raise ValueError("Current step must be 0 before a plan exists")
        else:
            if step_idx >= n_steps:
                raise ValueError(f"Current step {step_idx} is out of bounds for plan of length {n_steps}")
                
        self._current_step = step_idx

    def record_attempt(self, step_idx: int):
        if step_idx < 0:
            raise ValueError("Step index cannot be negative")
        current = self._per_step_attempts.get(step_idx, 0)
        if current + 1 > self._budget.max_attempts_per_step:
            raise ValueError(f"Attempts for step {step_idx} exceed maximum")
        self._per_step_attempts[step_idx] = current + 1

    def set_status(self, status: Any):
        if not isinstance(status, Status):
            try:
                status = Status(status)
            except ValueError:
                raise ValueError(f"Invalid status: {status}")
        self._status = status
        
    def add_artifact(self, artifact: Any):
        self._artifacts.append(artifact)
        
    def add_verification_result(self, result: Any):
        self._verification_results.append(result)
