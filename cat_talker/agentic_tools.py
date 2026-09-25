import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict

SCRATCHPAD_PENDING_ACTIONS: Dict[str, Dict[str, Any]] = {}


def read_file(path: str) -> str:
    file_path = Path(path).expanduser()
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return file_path.read_text(encoding="utf-8")


def ripgrep_search(query: str) -> str:
    try:
        result = subprocess.run(
            ["rg", "-n", query, "."],
            capture_output=True,
            text=True,
            check=False,
            cwd=os.getcwd(),
        )
        if result.stdout.strip():
            return result.stdout.strip()
        return "No matches found."
    except FileNotFoundError:
        return "rg is not installed. Install ripgrep if you want search support."


def execute_bash(action_id: str, command: str) -> str:
    SCRATCHPAD_PENDING_ACTIONS[action_id] = {
        "kind": "bash",
        "command": command,
        "status": "pending",
    }
    return f"Run this command?\n```bash\n{command}\n```"


def write_file(action_id: str, path: str, content: str) -> str:
    SCRATCHPAD_PENDING_ACTIONS[action_id] = {
        "kind": "write",
        "path": path,
        "content": content,
        "status": "pending",
    }
    return f"Write file: {path}?\n\nContent preview:\n```\n{content[:300]}\n```"


def approve_action(action_id: str):
    action = SCRATCHPAD_PENDING_ACTIONS.pop(action_id, None)
    if action is None:
        raise KeyError(f"Action {action_id} not found.")

    kind = action["kind"]
    if kind == "bash":
        result = subprocess.run(
            action["command"],
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout.strip() or result.stderr.strip() or "Command completed without output."
        return output

    if kind == "write":
        target = Path(action["path"]).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(action["content"], encoding="utf-8")
        return f"Wrote file: {target}"

    raise ValueError(f"Unsupported action kind: {kind}")


def reject_action(action_id: str):
    SCRATCHPAD_PENDING_ACTIONS.pop(action_id, None)
    return True
