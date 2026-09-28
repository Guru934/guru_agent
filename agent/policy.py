import datetime
import hashlib
import logging
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from agent.tool_registry import registry
from agent.capabilities import registry as capability_registry
from config import APP_DIR, DB_PATH, USER_STATE_DIR
from tools.workspace import resolve_workspace_path

logger = logging.getLogger(__name__)


@dataclass
class PolicyDecision:
    allowed: bool
    requires_approval: bool
    risk_level: str
    reason: str


class PolicyEngine:
    def __init__(self, safe_mode: bool = True):
        self.safe_mode = safe_mode
        self.blocked_executables = {
            "dd", "mkfs", "mkfs.btrfs", "mkfs.ext4", "mkfs.fat", "mkfs.xfs",
            "passwd", "reboot", "rm", "shutdown", "su", "sudo",
        }
        self.audit_file = USER_STATE_DIR / "security_audit.log"

    def _log_audit(self, tool_name: str, arguments: dict, target_risk: str, decision: PolicyDecision) -> bool:
        try:
            argument_summary = {}
            if "path" in arguments:
                argument_summary["path"] = str(arguments["path"])[:500]
            if "content" in arguments:
                argument_summary["content_length"] = len(str(arguments["content"]))
            for field in ("command", "query", "request"):
                if field in arguments:
                    argument_summary[f"{field}_sha256"] = hashlib.sha256(
                        str(arguments[field]).encode("utf-8")
                    ).hexdigest()
            timestamp = datetime.datetime.now().isoformat()
            log_line = (
                f"[{timestamp}] TOOL={tool_name} RISK={target_risk} "
                f"ALLOWED={decision.allowed} APPROVAL={decision.requires_approval} "
                f"REASON={decision.reason!r} ARGUMENTS={argument_summary!r}\n"
            )
            with open(self.audit_file, "a", encoding="utf-8") as audit:
                audit.write(log_line)
            return True
        except OSError:
            logger.exception("Unable to append to the security audit log.")
            return False

    def _is_path_allowed(
        self, path_str: str, cwd: Path = APP_DIR, workspace_root: Optional[Path] = None
    ) -> bool:
        try:
            resolve_workspace_path(path_str, cwd, allowed_root=workspace_root)
            return True
        except PermissionError:
            return False
        except (OSError, RuntimeError, ValueError):
            logger.exception("Unable to resolve path during workspace policy evaluation.")
            return False

    @staticmethod
    def _is_protected_path(path_str: str, cwd: Path = APP_DIR) -> bool:
        """Return whether a write target is part of Guru Agent's live installation/state."""
        try:
            target = Path(path_str).expanduser()
            if not target.is_absolute():
                target = cwd / target
            target = target.resolve()
            source_root = APP_DIR.resolve()
            protected_files = (
                DB_PATH.resolve(),
                (USER_STATE_DIR / "security_audit.log").resolve(),
            )
            if target == source_root or target.is_relative_to(source_root):
                return True
            if target in protected_files:
                return True
            if target.exists():
                # Without scanning the full source tree, reject writes through
                # any hard link so a source inode cannot be reached elsewhere.
                if target.stat().st_nlink > 1:
                    return True
                # Also catch alternate hard-link paths for protected state files.
                return any(
                    target.samefile(protected_file)
                    for protected_file in protected_files
                    if protected_file.exists()
                )
            return False
        except (OSError, RuntimeError, ValueError):
            logger.exception("Unable to resolve path during protected-path evaluation.")
            return True

    @staticmethod
    def _has_shell_operators(command: str) -> bool:
        return any(character in command for character in (";", "|", "&", "`", "$", "<", ">", "\n"))

    def _safe_path_arguments(
        self, tokens: Sequence[str], options: str = "", cwd: Path = APP_DIR,
        workspace_root: Optional[Path] = None,
    ) -> bool:
        for token in tokens:
            if token.startswith("-"):
                if not token[1:] or any(character not in options for character in token[1:]):
                    return False
            elif not self._is_path_allowed(token, cwd, workspace_root):
                return False
        return True

    def _is_safe_shell_command(
        self, command: str, tokens: Sequence[str], cwd: Path = APP_DIR,
        workspace_root: Optional[Path] = None,
    ) -> bool:
        if self._has_shell_operators(command):
            return False
        executable = Path(tokens[0]).name
        args = list(tokens[1:])

        if executable in {"pwd", "whoami"}:
            return not args
        if executable == "echo":
            return True
        if executable == "ls":
            return self._safe_path_arguments(args, options="lah", cwd=cwd, workspace_root=workspace_root)
        if executable == "cat":
            return bool(args) and all(self._is_path_allowed(arg, cwd, workspace_root) for arg in args)
        if executable == "git":
            return tokens in (["git", "status"], ["git", "diff"], ["git", "log"])
        return False

    def _check_capability_grant(self, tool_name: str, arguments: dict) -> bool:
        """Check if there's a capability grant that allows this tool execution without approval."""
        grant = capability_registry.check_grant(tool_name, arguments)
        return grant is not None

    def _evaluate_shell(
        self, command: str, risk: str, cwd: Path = APP_DIR,
        workspace_root: Optional[Path] = None,
    ) -> PolicyDecision:
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError as error:
            return PolicyDecision(False, False, "high", f"Invalid shell command syntax: {error}")
        if not tokens:
            return PolicyDecision(False, False, "low", "Empty shell commands are not allowed.")

        executable = Path(tokens[0]).name.lower()
        if executable in self.blocked_executables or executable.startswith("mkfs."):
            return PolicyDecision(False, False, "critical", f"Execution of {executable!r} is blocked by policy.")
        if executable in {"chmod", "chown"} and any(arg in {"-R", "--recursive"} for arg in tokens[1:]):
            return PolicyDecision(False, False, "critical", f"Recursive {executable} operations are blocked by policy.")

        if self._is_safe_shell_command(command, tokens, cwd, workspace_root):
            return PolicyDecision(True, False, "low", "Command matches the restricted read-only command policy.")
        if self.safe_mode:
            return PolicyDecision(
                True,
                True,
                risk,
                "Command is outside the restricted read-only allowlist and requires explicit approval.",
            )
        return PolicyDecision(True, False, risk, "Safe mode is disabled; command is permitted by user preference.")

    def evaluate(self, tool_name: str, arguments: dict, context: dict, tool_registry=registry) -> PolicyDecision:
        workspace_root = context.get("workspace_dir")
        cwd = Path(workspace_root) if workspace_root else APP_DIR
        spec = tool_registry.get_spec(tool_name)
        if not spec:
            decision = PolicyDecision(False, False, "unknown", f"Tool {tool_name} is not registered.")
            self._log_audit(tool_name, arguments, "unknown", decision)
            return decision

        risk = spec.risk
        if context.get("require_project") and not workspace_root and tool_name in {
            "execute_shell", "read_file", "write_file", "search"
        }:
            decision = PolicyDecision(
                False, False, "critical",
                "Repository and file operations require a selected active project.",
            )
        elif tool_name == "execute_shell":
            decision = self._evaluate_shell(str(arguments.get("command", "")), risk, cwd, workspace_root)
        elif tool_name == "write_file":
            path = arguments.get("path", "")
            if self._is_protected_path(path, cwd):
                decision = PolicyDecision(
                    False, False, "critical",
                    f"Path {path!r} is protected from modification by Guru Agent tools."
                )
            elif not self._is_path_allowed(path, cwd, workspace_root):
                decision = PolicyDecision(
                    False, False, "critical",
                    f"Path {path!r} is outside the allowed workspace roots."
                )
            elif risk in {"high", "medium"} and self.safe_mode:
                decision = PolicyDecision(
                    True, True, risk, f"Safe mode requires manual approval for {risk}-risk actions."
                )
            else:
                decision = PolicyDecision(True, False, risk, f"{risk.capitalize()}-risk action allowed.")
        elif tool_name == "read_file":
            path = arguments.get("path", "")
            if not self._is_path_allowed(path, cwd, workspace_root):
                decision = PolicyDecision(
                    False, False, "critical",
                    f"Path {path!r} is outside the allowed workspace roots."
                )
            else:
                decision = PolicyDecision(True, False, risk, "Low-risk action allowed.")
        else:
            decision = PolicyDecision(
                True,
                risk in {"high", "medium"} and self.safe_mode,
                risk,
                f"Safe mode requires manual approval for {risk}-risk actions."
                if risk in {"high", "medium"} and self.safe_mode
                else f"{risk.capitalize()}-risk action allowed.",
            )

        # Check capability grants - if a grant exists, remove approval requirement
        if decision.requires_approval and self._check_capability_grant(tool_name, arguments):
            decision = PolicyDecision(
                True,
                False,
                risk,
                f"Allowed by capability grant (no approval required)."
            )

        if not self._log_audit(tool_name, arguments, risk, decision):
            return PolicyDecision(
                False,
                False,
                "critical",
                "Security audit could not be written; tool execution is denied.",
            )
        return decision


engine = PolicyEngine(safe_mode=True)
