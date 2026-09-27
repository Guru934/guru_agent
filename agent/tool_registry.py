import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict

SCRATCHPAD_PENDING_ACTIONS: Dict[str, Dict[str, Any]] = {}


def read_file(path: str) -> str:
    from tools.filesystem import read_file
    return read_file(path)


def ripgrep_search(query: str) -> str:
    from tools.shell import ripgrep_search_impl
    return ripgrep_search_impl(query)


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
        from tools.shell import execute_bash_command
        return execute_bash_command(action["command"])

    if kind == "write":
        from tools.filesystem import write_file_content
        return write_file_content(action["path"], action["content"])

    raise ValueError(f"Unsupported action kind: {kind}")


def reject_action(action_id: str):
    SCRATCHPAD_PENDING_ACTIONS.pop(action_id, None)
    return True
