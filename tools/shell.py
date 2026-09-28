import os
import selectors
import signal
import subprocess
from agent.events import emit
import sys
import time
from pathlib import Path

from config import APP_DIR, WORKSPACE_ROOTS

MAX_COMMAND_OUTPUT = 12_000
COMMAND_TIMEOUT_SECONDS = 30


def _command_environment():
    executable_dir = str(Path(sys.executable).resolve().parent)
    return {
        "PATH": os.pathsep.join((executable_dir, "/usr/local/bin", "/usr/bin", "/bin")),
        "HOME": str(APP_DIR),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }

def execute_bash_command(command: str, _task_id: str = None, _workspace_dir=None) -> str:
    if _task_id:
        emit("SHELL_COMMAND", _task_id, {"command": command})

    process = subprocess.Popen(
        command,
        shell=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(_workspace_dir or APP_DIR),
        env=_command_environment(),
        start_new_session=True,
        bufsize=0,
    )
    if process.stdout is None:
        process.kill()
        process.wait()
        raise RuntimeError("Shell command output pipe could not be opened.")

    output = bytearray()
    truncated = False
    deadline = time.monotonic() + COMMAND_TIMEOUT_SECONDS
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, COMMAND_TIMEOUT_SECONDS, output=bytes(output))
            for key, _ in selector.select(remaining):
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                room = MAX_COMMAND_OUTPUT - len(output)
                output.extend(chunk[:room])
                truncated = truncated or len(chunk) > room
                if _task_id and chunk:
                    try:
                        text_chunk = chunk.decode("utf-8", errors="replace")
                        emit("SHELL_OUTPUT", _task_id, {"chunk": text_chunk})
                    except Exception:
                        pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, COMMAND_TIMEOUT_SECONDS, output=bytes(output))
        return_code = process.wait(timeout=remaining)
        if _task_id:
            emit("SHELL_EXIT", _task_id, {"exit_code": return_code})
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise
    finally:
        selector.close()
        process.stdout.close()

    text = output.decode("utf-8", errors="replace").strip()
    if truncated:
        text += "\n[Output truncated.]"
    if not text:
        text = "Command completed without output."
    if return_code:
        return f"Command exited with status {return_code}.\n{text}"
    return text

def ripgrep_search_impl(query: str, _workspace_dir=None) -> str:
    all_output = []
    roots = [_workspace_dir] if _workspace_dir is not None else WORKSPACE_ROOTS
    for root in roots:
        if not root.exists():
            continue
        result = subprocess.run(
            ["rg", "-n", query, "."],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(root),
            env=_command_environment(),
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
        if result.returncode == 1:
            continue
        if result.returncode:
            raise RuntimeError(f"ripgrep failed with status {result.returncode}: {result.stderr.strip()}")
        output = result.stdout.strip()
        if output:
            all_output.append(f"=== {root} ===\n{output}")
    
    if not all_output:
        return "No matches found."
    
    combined = "\n\n".join(all_output)
    if len(combined) > MAX_COMMAND_OUTPUT:
        combined = combined[:MAX_COMMAND_OUTPUT] + "\n[Output truncated.]"
    return combined
