import json
import heapq
import math
import os
import selectors
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional, Sequence

from agent.tool_result import ToolResult
from config import MAX_WRITE_BYTES
from tools.filesystem import read_file, write_file_content
from tools.shell import _command_environment, ripgrep_search_impl
from tools.workspace import resolve_workspace_path


MAX_CODING_OUTPUT_BYTES = 12_000
MAX_COMMAND_TIMEOUT = 300.0
_HEAD_BYTES = MAX_CODING_OUTPUT_BYTES // 2
_TAIL_BYTES = MAX_CODING_OUTPUT_BYTES - _HEAD_BYTES


def _result(
    ok: bool,
    summary: str,
    details: str = "",
    *,
    changed: bool = False,
    artifact: Optional[str] = None,
    truncated: bool = False,
) -> ToolResult:
    return ToolResult(ok, summary, details, changed, artifact, truncated)


def _project_root(workspace_dir) -> Path:
    if workspace_dir is None:
        raise PermissionError("Coding tools require an active project workspace.")
    root = Path(workspace_dir).resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Project workspace is not a directory: {root}")
    resolve_workspace_path(".", base_dir=root, allowed_root=root)
    return root


def _project_path(path: str, root: Path) -> Path:
    target = resolve_workspace_path(path, base_dir=root, allowed_root=root)
    return target


def _safe_glob(pattern: str) -> bool:
    candidate = Path(pattern)
    return bool(pattern) and not candidate.is_absolute() and ".." not in candidate.parts


def _protected_file(path: Path, root: Path) -> bool:
    from agent.policy import PolicyEngine

    return PolicyEngine._is_protected_path(str(path), root)


def _bounded_bytes(head: bytes, tail: bytes, truncated: bool) -> str:
    if not truncated:
        return head.decode("utf-8", errors="replace")
    head_lines = head.decode("utf-8", errors="replace").splitlines(keepends=True)[:50]
    tail_lines = tail.decode("utf-8", errors="replace").splitlines(keepends=True)[-50:]
    return "".join(head_lines) + "\n[Output truncated; showing beginning and end.]\n" + "".join(tail_lines)


def _run_argv(
    argv: Sequence[str], cwd: Path, timeout: float, output_limit: int = MAX_CODING_OUTPUT_BYTES
):
    """Run argv without a shell while retaining bounded head/tail output."""
    environment = _command_environment()
    environment["HOME"] = str(cwd)
    process = subprocess.Popen(
        list(argv),
        cwd=str(cwd),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        bufsize=0,
    )
    if process.stdout is None:
        process.kill()
        process.wait()
        raise RuntimeError("Command output pipe could not be opened.")

    head_limit = output_limit // 2
    tail_limit = output_limit - head_limit
    captured = bytearray()
    head = bytearray()
    tail = bytearray()
    total_bytes = 0
    truncated = False
    timed_out = False
    deadline = time.monotonic() + timeout
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0 and not timed_out:
                timed_out = True
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            events = selector.select(0.05 if timed_out else min(0.05, remaining))
            for key, _ in events:
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                total_bytes += len(chunk)
                if not truncated and total_bytes <= output_limit:
                    captured.extend(chunk)
                    continue
                if not truncated:
                    truncated = True
                    head.extend(captured[:head_limit])
                    tail.extend(captured[head_limit:])
                    captured.clear()
                if len(head) < head_limit:
                    take = min(head_limit - len(head), len(chunk))
                    head.extend(chunk[:take])
                    chunk = chunk[take:]
                if chunk:
                    tail.extend(chunk)
                    if len(tail) > tail_limit:
                        del tail[:-tail_limit]
        try:
            return_code = process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return_code = process.wait()
    finally:
        selector.close()
        process.stdout.close()

    if not truncated:
        output = bytes(captured).decode("utf-8", errors="replace")
    else:
        output = _bounded_bytes(bytes(head), bytes(tail), True)
    return return_code, output, truncated, timed_out


def _validate_timeout(timeout) -> Optional[str]:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout):
        return "timeout must be a finite positive number of seconds."
    if timeout <= 0 or timeout > MAX_COMMAND_TIMEOUT:
        return f"timeout must be greater than 0 and no more than {MAX_COMMAND_TIMEOUT:g} seconds."
    return None


def list_files(glob: str = "**/*", max: int = 200, _workspace_dir=None) -> ToolResult:
    try:
        root = _project_root(_workspace_dir)
        if not _safe_glob(glob):
            return _result(False, "glob must be a relative pattern within the active project.")
        if isinstance(max, bool) or not isinstance(max, int) or max < 1:
            return _result(False, "max must be a positive integer.")
        limit = min(max, 200)
        def candidates():
            for match in root.glob(glob):
                if ".git" in match.relative_to(root).parts:
                    continue
                try:
                    resolved = match.resolve(strict=True)
                    if resolved != root and not resolved.is_relative_to(root):
                        continue
                    if not resolved.is_file() or _protected_file(resolved, root):
                        continue
                except (OSError, RuntimeError, ValueError):
                    continue
                yield match.relative_to(root).as_posix()

        files = heapq.nsmallest(limit + 1, candidates())
        truncated = len(files) > limit
        shown = files[:limit]
        details = "\n".join(shown)
        return _result(
            True,
            f"Listed {len(shown)} file(s) in the active project.",
            details,
            artifact=json.dumps({"files": shown}),
            truncated=truncated,
        )
    except (OSError, RuntimeError, ValueError, PermissionError) as error:
        return _result(False, str(error))


def coding_read_file(
    path: str, start_line: Optional[int] = None, end_line: Optional[int] = None,
    _workspace_dir=None,
) -> ToolResult:
    try:
        if _workspace_dir is None:
            content = read_file(path, start_line, end_line)
            return _result(True, f"Read {path}.", content, artifact=path)
        root = _project_root(_workspace_dir)
        _project_path(path, root)
        content = read_file(path, start_line, end_line, root)
        line_range = ""
        if start_line is not None or end_line is not None:
            line_range = f" (lines {start_line or 1}-{end_line or 'end'})"
        return _result(True, f"Read {path}{line_range}.", content, artifact=path)
    except (OSError, RuntimeError, ValueError, PermissionError) as error:
        return _result(False, str(error))


def search(
    query: str, path: Optional[str] = None, glob: Optional[str] = None, _workspace_dir=None
) -> ToolResult:
    try:
        if _workspace_dir is None:
            if path is not None or glob is not None:
                return _result(False, "Filtered search requires an active project workspace.")
            legacy_output = ripgrep_search_impl(query)
            return _result(True, "Search completed.", legacy_output)
        root = _project_root(_workspace_dir)
        search_path = _project_path(path or ".", root)
        if not search_path.exists():
            return _result(False, f"Search path does not exist: {path or '.'}")
        if glob is not None and not _safe_glob(glob):
            return _result(False, "glob must be a relative pattern within the active project.")
        relative_path = search_path.relative_to(root).as_posix() or "."
        argv = ["rg", "--line-number", "--no-heading", "--color", "never"]
        if glob is not None:
            argv.extend(["--glob", glob])
        argv.extend(["--", query, relative_path])
        return_code, output, truncated, timed_out = _run_argv(argv, root, timeout=10)
        if timed_out:
            return _result(False, "Search timed out.", output, truncated=truncated)
        if return_code == 1:
            return _result(True, "No matches found.", truncated=truncated)
        if return_code != 0:
            return _result(False, f"ripgrep exited with status {return_code}.", output, truncated=truncated)
        return _result(True, "Search completed.", output, artifact=relative_path, truncated=truncated)
    except FileNotFoundError as error:
        return _result(False, f"Required search executable is unavailable: {error}")
    except (OSError, RuntimeError, ValueError, PermissionError) as error:
        return _result(False, str(error))


def replace_in_file(path: str, old: str, new: str, _workspace_dir=None) -> ToolResult:
    try:
        root = _project_root(_workspace_dir)
        target = _project_path(path, root)
        if _protected_file(target, root):
            return _result(False, f"Path {path!r} is protected from modification.")
        if not old:
            return _result(False, "old must be non-empty to avoid ambiguous insertion matches.")
        content = read_file(path, _workspace_dir=root)
        first_match = content.find(old)
        if first_match < 0:
            return _result(False, "old matched zero times; file was not changed.")
        second_match = content.find(old, first_match + 1)
        if second_match >= 0:
            return _result(False, "old matched multiple times; file was not changed.")
        if old == new:
            return _result(True, "Exactly one match found; replacement is unchanged.", changed=False, artifact=path)
        updated = content.replace(old, new, 1)
        if len(updated.encode("utf-8")) > MAX_WRITE_BYTES:
            return _result(False, f"Replacement exceeds maximum write limit ({MAX_WRITE_BYTES} bytes).")
        write_file_content(path, updated, _workspace_dir=root)
        return _result(True, f"Replaced one match in {path}.", changed=True, artifact=path)
    except (OSError, RuntimeError, ValueError, PermissionError) as error:
        return _result(False, str(error))


def _git_root(workspace_dir) -> Path:
    root = _project_root(workspace_dir)
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if result.returncode:
        raise ValueError("The active project is not a Git repository.")
    git_root = Path(result.stdout.strip()).resolve()
    if git_root != root:
        raise PermissionError("Git operations must run at the active project root.")
    return root


def git_status(_workspace_dir=None) -> ToolResult:
    try:
        root = _git_root(_workspace_dir)
        code, output, truncated, timed_out = _run_argv(
            ["git", "status", "--porcelain=v1", "-b", "--untracked-files=all"], root, timeout=5
        )
        if timed_out or code:
            return _result(False, "git status failed or timed out.", output, truncated=truncated)
        lines = output.splitlines()
        branch = lines[0][3:] if lines and lines[0].startswith("## ") else ""
        entries = lines[1:] if branch else lines
        status = {"repository": str(root), "branch": branch, "entries": entries, "clean": not entries}
        summary = "Working tree clean." if not entries else f"Working tree has {len(entries)} change(s)."
        return _result(True, summary, output, artifact=json.dumps(status), truncated=truncated)
    except (OSError, RuntimeError, ValueError, PermissionError) as error:
        return _result(False, str(error))


def git_diff(_workspace_dir=None) -> ToolResult:
    try:
        root = _git_root(_workspace_dir)
        code, output, truncated, timed_out = _run_argv(
            ["git", "diff", "--no-ext-diff", "--no-color", "--"], root, timeout=10
        )
        if timed_out or code:
            return _result(False, "git diff failed or timed out.", output, truncated=truncated)
        summary = "Git diff is empty." if not output else "Git diff retrieved."
        return _result(True, summary, output, artifact=str(root), truncated=truncated)
    except (OSError, RuntimeError, ValueError, PermissionError) as error:
        return _result(False, str(error))


def run_command(
    argv: list[str], cwd: str, timeout: float, _workspace_dir=None
) -> ToolResult:
    try:
        root = _project_root(_workspace_dir)
        timeout_error = _validate_timeout(timeout)
        if timeout_error:
            return _result(False, timeout_error)
        if not isinstance(argv, list) or not argv or any(not isinstance(item, str) for item in argv):
            return _result(False, "argv must be a non-empty list of strings.")
        if not argv[0]:
            return _result(False, "argv[0] must name an executable.")
        workdir = _project_path(cwd, root)
        if not workdir.is_dir():
            return _result(False, "cwd must be an existing directory inside the active project.")
        executable = Path(argv[0]).name.lower()
        if executable in {"rm", "sudo", "su", "dd", "passwd", "reboot", "shutdown"} or executable.startswith("mkfs"):
            return _result(False, f"Execution of {executable!r} is blocked by policy.")
        return_code, output, truncated, timed_out = _run_argv(argv, workdir, float(timeout))
        artifact = json.dumps({"argv": argv, "cwd": str(workdir), "returncode": return_code})
        if timed_out:
            return _result(False, f"Command timed out after {timeout:g} seconds.", output, artifact=artifact, truncated=truncated)
        if return_code != 0:
            return _result(False, f"Command exited with status {return_code}.", output, artifact=artifact, truncated=truncated)
        return _result(True, "Command completed successfully.", output, changed=True, artifact=artifact, truncated=truncated)
    except FileNotFoundError as error:
        return _result(False, f"Command executable or cwd was not found: {error}")
    except (OSError, RuntimeError, ValueError, PermissionError) as error:
        return _result(False, str(error))
