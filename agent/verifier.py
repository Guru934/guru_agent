"""Deterministic repository verification through the existing tool boundary."""

import configparser
import importlib.util
import json
import math
import os
import shutil
import site
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent.executor import ToolExecutor
from agent.tool_registry import registry
from agent.tool_result import ToolResult
from memory.sqlite import get_active_project, validate_project_path


@dataclass(frozen=True)
class VerificationCommand:
    name: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class CommandVerdict:
    command: VerificationCommand
    exit_status: Optional[int]
    output: str
    truncated: bool
    timed_out: bool
    error: Optional[str]

    @property
    def passed(self) -> bool:
        return self.exit_status == 0 and not self.timed_out and self.error is None


@dataclass(frozen=True)
class VerificationAttempt:
    number: int
    commands: tuple[CommandVerdict, ...]

    @property
    def passed(self) -> bool:
        return bool(self.commands) and all(command.passed for command in self.commands)


@dataclass(frozen=True)
class Verdict:
    passed: bool
    step: str
    repository: Optional[Path]
    attempts: tuple[VerificationAttempt, ...]
    retried: bool
    summary: str
    detection_errors: tuple[str, ...] = ()

    @property
    def commands_executed(self) -> tuple[CommandVerdict, ...]:
        return tuple(command for attempt in self.attempts for command in attempt.commands)


class Verifier:
    def __init__(
        self,
        executor: Optional[ToolExecutor] = None,
        timeout_seconds: float = 300,
        command_lookup=None,
    ):
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
            or timeout_seconds > 300
        ):
            raise ValueError("timeout_seconds must be greater than 0 and no more than 300.")
        self.executor = executor or ToolExecutor(registry)
        self.timeout_seconds = timeout_seconds
        self.command_lookup = command_lookup

    def _which(self, name: str) -> Optional[str]:
        return self.command_lookup(name) if self.command_lookup else shutil.which(name)

    def _project_tool(self, root: Path, name: str) -> Optional[str]:
        local = root / ".venv" / "bin" / name
        if local.is_file() and os.access(local, os.X_OK):
            return str(local)
        return self._which(name)

    @staticmethod
    def _resolve_repository(repo_root) -> Path:
        repository = get_active_project() if repo_root is None else validate_project_path(str(repo_root))
        if repository is None:
            raise ValueError("No valid active project is selected for verification.")
        return Path(repository).resolve(strict=True)

    @staticmethod
    def _read_pyproject(root: Path) -> dict:
        path = root / "pyproject.toml"
        if not path.is_file():
            return {}
        try:
            with path.open("rb") as source:
                return tomllib.load(source)
        except (OSError, tomllib.TOMLDecodeError):
            return {}

    @staticmethod
    def _has_mypy_config(root: Path, pyproject: dict) -> bool:
        if isinstance(pyproject.get("tool", {}).get("mypy"), dict):
            return True
        for filename in ("mypy.ini", ".mypy.ini", "setup.cfg"):
            path = root / filename
            if not path.is_file():
                continue
            parser = configparser.ConfigParser()
            try:
                parser.read(path, encoding="utf-8")
            except (OSError, configparser.Error):
                continue
            if parser.has_section("mypy"):
                return True
        return False

    @staticmethod
    def _has_ruff_config(root: Path, pyproject: dict) -> bool:
        return (
            isinstance(pyproject.get("tool", {}).get("ruff"), dict)
            or (root / "ruff.toml").is_file()
            or (root / ".ruff.toml").is_file()
        )

    @staticmethod
    def _has_python_tests(root: Path) -> bool:
        for directory in (root / "tests", root / "test"):
            if directory.is_dir():
                if any(directory.rglob("test_*.py")) or any(directory.rglob("*_test.py")):
                    return True
        return any(root.glob("test_*.py")) or any(root.glob("*_test.py"))

    @staticmethod
    def _pytest_argv(root: Path) -> Optional[tuple[str, ...]]:
        test_path = "tests" if (root / "tests").is_dir() else "."
        local_pytest = root / ".venv" / "bin" / "pytest"
        if local_pytest.is_file() and os.access(local_pytest, os.X_OK):
            return (str(local_pytest), "-q", test_path)
        try:
            pytest_available = importlib.util.find_spec("pytest") is not None
        except (ImportError, ValueError):
            pytest_available = False
        if pytest_available:
            # M2 deliberately runs commands with HOME set to the project. Add
            # the agent interpreter's installed pytest site explicitly without
            # changing the command environment or crossing the tool boundary.
            bootstrap = (
                "import os,site,sys; site.addsitedir(sys.argv[1]); "
                "root=os.path.realpath(os.getcwd()); "
                "sys.path[:]=[p for p in sys.path if os.path.realpath(p or root)!=root]; "
                "import math,pytest; sys.path.insert(0,root); "
                "raise SystemExit(pytest.main(sys.argv[2:]))"
            )
            return (
                sys.executable,
                "-c",
                bootstrap,
                str(site.getusersitepackages()),
                "-q",
                test_path,
            )
        return None

    def _detect(self, root: Path) -> tuple[list[VerificationCommand], list[str]]:
        commands: list[VerificationCommand] = []
        issues: list[str] = []
        pyproject = self._read_pyproject(root)
        python_project = any(
            (root / marker).exists()
            for marker in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
        ) or (root / "tests").is_dir()

        if python_project:
            if self._has_python_tests(root):
                pytest_argv = self._pytest_argv(root)
                if pytest_argv:
                    commands.append(VerificationCommand("pytest", pytest_argv))
                else:
                    issues.append("Python tests exist, but pytest is unavailable.")

            ruff_configured = self._has_ruff_config(root, pyproject)
            ruff = self._project_tool(root, "ruff")
            if ruff:
                commands.append(VerificationCommand("ruff", (ruff, "check", ".")))
            elif ruff_configured:
                issues.append("Ruff is configured, but the ruff executable is unavailable.")

            mypy_configured = self._has_mypy_config(root, pyproject)
            mypy = self._project_tool(root, "mypy")
            if mypy_configured and mypy:
                commands.append(VerificationCommand("mypy", (mypy, ".")))
            elif mypy_configured:
                issues.append("Mypy is configured, but the mypy executable is unavailable.")

        package_path = root / "package.json"
        if package_path.is_file():
            try:
                package = json.loads(package_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                issues.append(f"Unable to read package.json: {error}")
                package = {}
            scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
            if isinstance(scripts, dict):
                package_manager = self._package_manager(root, package)
                manager_path = self._which(package_manager)
                for script in ("test", "lint"):
                    if not isinstance(scripts.get(script), str) or not scripts[script].strip():
                        continue
                    if manager_path:
                        commands.append(
                            VerificationCommand(
                                f"{package_manager} run {script}",
                                (manager_path, "run", script),
                            )
                        )
                    else:
                        issues.append(
                            f"package.json defines {script!r}, but {package_manager} is unavailable."
                        )

        if (root / "Cargo.toml").is_file():
            cargo = self._which("cargo")
            if cargo:
                commands.append(VerificationCommand("cargo test", (cargo, "test")))
                clippy = self._which("cargo-clippy")
                if clippy:
                    commands.append(VerificationCommand("cargo clippy", (cargo, "clippy")))
                else:
                    issues.append("Rust project found, but cargo-clippy is unavailable.")
            else:
                issues.append("Cargo.toml found, but the cargo executable is unavailable.")

        return commands, issues

    @staticmethod
    def _package_manager(root: Path, package: dict) -> str:
        declared = package.get("packageManager", "")
        if isinstance(declared, str) and declared.split("@", 1)[0] in {"npm", "pnpm", "yarn"}:
            return declared.split("@", 1)[0]
        if (root / "pnpm-lock.yaml").exists():
            return "pnpm"
        if (root / "yarn.lock").exists():
            return "yarn"
        return "npm"

    def detect_commands(self, repo_root) -> list[VerificationCommand]:
        root = self._resolve_repository(repo_root)
        commands, _ = self._detect(root)
        return commands

    @staticmethod
    def _step_text(step) -> str:
        if isinstance(step, str):
            return step
        return str(getattr(step, "description", step))

    def _execute(self, command: VerificationCommand, root: Path, task_id: str) -> CommandVerdict:
        try:
            execution = self.executor.execute(
                "run_command",
                {
                    "argv": list(command.argv),
                    "cwd": str(root),
                    "timeout": self.timeout_seconds,
                },
                {"task_id": task_id, "workspace_dir": root, "require_project": True},
            )
            result = execution.output
            if isinstance(result, ToolResult):
                exit_status = None
                if result.artifact:
                    try:
                        exit_status = json.loads(result.artifact).get("returncode")
                    except (json.JSONDecodeError, AttributeError):
                        pass
                error = None if execution.status == "success" and result.ok else result.summary
                return CommandVerdict(
                    command,
                    exit_status,
                    result.details or result.summary,
                    result.truncated,
                    "timed out" in result.summary.casefold(),
                    error,
                )
            return CommandVerdict(command, None, str(result), False, False, str(result))
        except Exception as error:
            return CommandVerdict(command, None, str(error), False, False, str(error))

    def check(self, step, repo_root) -> Verdict:
        step_text = self._step_text(step)
        try:
            root = self._resolve_repository(repo_root)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            return Verdict(False, step_text, None, (), False, str(error), (str(error),))

        commands, issues = self._detect(root)
        if issues:
            return Verdict(
                False,
                step_text,
                root,
                (),
                False,
                "Verification could not start because required configured tools are unavailable.",
                tuple(issues),
            )
        if not commands:
            issue = "No supported, available verification commands were detected for this repository."
            return Verdict(False, step_text, root, (), False, issue, (issue,))

        import uuid

        task_id = f"verify-{uuid.uuid4()}"
        attempts: list[VerificationAttempt] = []
        for attempt_number in (1, 2):
            outcomes = tuple(self._execute(command, root, task_id) for command in commands)
            attempt = VerificationAttempt(attempt_number, outcomes)
            attempts.append(attempt)
            if attempt.passed:
                retried = attempt_number == 2
                summary = "Verification passed after one retry." if retried else "Verification passed."
                return Verdict(True, step_text, root, tuple(attempts), retried, summary)

        return Verdict(
            False,
            step_text,
            root,
            tuple(attempts),
            True,
            "Verification failed after the initial attempt and one retry.",
        )


def detect_commands(repo_root) -> list[VerificationCommand]:
    return Verifier().detect_commands(repo_root)


def check(step, repo_root) -> Verdict:
    return Verifier().check(step, repo_root)
