from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass
from tools.coding import (
    coding_read_file,
    git_diff,
    git_status,
    list_files,
    replace_in_file,
    run_command,
    search as search_project,
)
from tools.shell import execute_bash_command, ripgrep_search_impl
from tools.filesystem import write_file_content
from tools.desktop import (
    open_application, open_website, set_volume, set_brightness,
    get_clipboard, search_and_play_youtube, handle_desktop_action
)
from tools.browser import describe_active_window, describe_current_screen

@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    risk: str
    handler: Callable
    
class Registry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec):
        self._tools[spec.name] = spec
        
    def get_tool(self, name: str) -> Optional[Callable]:
        spec = self._tools.get(name)
        if spec:
            return spec.handler
        return None
        
    def get_spec(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)
        
    def get_all_specs(self):
        return list(self._tools.values())


def validate_arguments(schema: dict, arguments: Any, path: str = "arguments") -> Optional[str]:
    if not isinstance(arguments, dict):
        return f"{path} must be an object."

    properties = schema.get("properties", {})
    required = schema.get("required", [])
    missing = [name for name in required if name not in arguments]
    if missing:
        return f"{path} is missing required field(s): {', '.join(missing)}."

    if schema.get("additionalProperties", True) is False:
        unexpected = [name for name in arguments if name not in properties]
        if unexpected:
            return f"{path} contains unsupported field(s): {', '.join(unexpected)}."

    for name, value in arguments.items():
        if name not in properties:
            continue
        error = _validate_value(properties[name], value, f"{path}.{name}")
        if error:
            return error
    return None


def _validate_value(schema: dict, value: Any, path: str) -> Optional[str]:
    expected = schema.get("type")
    type_checks = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
    }
    check = type_checks.get(expected)
    if check is None:
        return f"{path} uses unsupported schema type {expected!r}."
    if not check(value):
        return f"{path} must be {expected}."
    if expected == "object":
        return validate_arguments(schema, value, path)
    if expected == "array":
        item_schema = schema.get("items")
        if item_schema is None:
            return f"{path} has no declared item schema."
        for index, item in enumerate(value):
            error = _validate_value(item_schema, item, f"{path}[{index}]")
            if error:
                return error
    if "enum" in schema and value not in schema["enum"]:
        return f"{path} must be one of {schema['enum']}."
    return None


registry = Registry()

registry.register(ToolSpec(
    name="execute_shell",
    description="Executes a bash/terminal command and returns output.",
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string"}
        },
        "required": ["command"],
        "additionalProperties": False,
    },
    risk="high",
    handler=lambda command, _task_id=None, _workspace_dir=None: execute_bash_command(
        command, _task_id, _workspace_dir
    )
))

registry.register(ToolSpec(
    name="write_file",
    description="Writes content to a specific file path.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"}
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    },
    risk="medium",
    handler=lambda path, content, _workspace_dir=None: write_file_content(path, content, _workspace_dir)
))

registry.register(ToolSpec(
    name="read_file",
    description="Reads the contents of a file.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    risk="low",
    handler=lambda path, start_line=None, end_line=None, _workspace_dir=None: coding_read_file(
        path, start_line, end_line, _workspace_dir
    )
))

registry.register(ToolSpec(
    name="search",
    description="Search files linearly for a query string.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "path": {"type": "string"},
            "glob": {"type": "string"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    risk="low",
    handler=lambda query, path=None, glob=None, _workspace_dir=None: search_project(
        query, path, glob, _workspace_dir
    )
))

registry.register(ToolSpec(
    name="list_files",
    description="List files in the active project using a relative glob pattern.",
    input_schema={
        "type": "object",
        "properties": {
            "glob": {"type": "string"},
            "max": {"type": "integer"},
        },
        "required": ["glob"],
        "additionalProperties": False,
    },
    risk="low",
    handler=lambda glob, max=200, _workspace_dir=None: list_files(glob, max, _workspace_dir),
))

registry.register(ToolSpec(
    name="replace_in_file",
    description="Replace exactly one occurrence of text in an active-project file.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old": {"type": "string"},
            "new": {"type": "string"},
        },
        "required": ["path", "old", "new"],
        "additionalProperties": False,
    },
    risk="medium",
    handler=lambda path, old, new, _workspace_dir=None: replace_in_file(
        path, old, new, _workspace_dir
    ),
))

registry.register(ToolSpec(
    name="git_status",
    description="Return structured Git status for the active project.",
    input_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    risk="low",
    handler=lambda _workspace_dir=None: git_status(_workspace_dir),
))

registry.register(ToolSpec(
    name="git_diff",
    description="Return a bounded Git diff for the active project.",
    input_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    risk="low",
    handler=lambda _workspace_dir=None: git_diff(_workspace_dir),
))

registry.register(ToolSpec(
    name="run_command",
    description="Run an argv command in an explicitly selected active-project directory.",
    input_schema={
        "type": "object",
        "properties": {
            "argv": {"type": "array", "items": {"type": "string"}},
            "cwd": {"type": "string"},
            "timeout": {"type": "number"},
        },
        "required": ["argv", "cwd", "timeout"],
        "additionalProperties": False,
    },
    risk="high",
    handler=lambda argv, cwd, timeout, _workspace_dir=None: run_command(
        argv, cwd, timeout, _workspace_dir
    ),
))

registry.register(ToolSpec(
    name="open_application",
    description="Open a desktop application by name (e.g., 'chrome', 'code', 'terminal').",
    input_schema={
        "type": "object",
        "properties": {
            "app_name": {"type": "string", "description": "Name of the application to open"}
        },
        "required": ["app_name"],
        "additionalProperties": False,
    },
    risk="high",
    handler=lambda app_name: open_application(app_name)
))

registry.register(ToolSpec(
    name="open_website",
    description="Open a website URL in the default browser.",
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to open (e.g., 'https://youtube.com')"}
        },
        "required": ["url"],
        "additionalProperties": False,
    },
    risk="high",
    handler=lambda url: open_website(url)
))

registry.register(ToolSpec(
    name="set_volume",
    description="Set system volume level (0-100).",
    input_schema={
        "type": "object",
        "properties": {
            "level_percent": {"type": "integer", "minimum": 0, "maximum": 100, "description": "Volume level 0-100"}
        },
        "required": ["level_percent"],
        "additionalProperties": False,
    },
    risk="medium",
    handler=lambda level_percent: set_volume(level_percent)
))

registry.register(ToolSpec(
    name="set_brightness",
    description="Set screen brightness level (0-100).",
    input_schema={
        "type": "object",
        "properties": {
            "level_percent": {"type": "integer", "minimum": 0, "maximum": 100, "description": "Brightness level 0-100"}
        },
        "required": ["level_percent"],
        "additionalProperties": False,
    },
    risk="medium",
    handler=lambda level_percent: set_brightness(level_percent)
))

registry.register(ToolSpec(
    name="get_clipboard",
    description="Get the current clipboard contents.",
    input_schema={
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
    risk="low",
    handler=lambda: get_clipboard()
))

registry.register(ToolSpec(
    name="search_and_play_youtube",
    description="Search YouTube and play the first result.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query for YouTube"}
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    risk="high",
    handler=lambda query: search_and_play_youtube(query)
))

# Legacy fallback - kept for backward compatibility
registry.register(ToolSpec(
    name="desktop_action",
    description="[Legacy] Perform a desktop action from free-text request. Use granular tools instead.",
    input_schema={
        "type": "object",
        "properties": {
            "request": {"type": "string"}
        },
        "required": ["request"],
        "additionalProperties": False,
    },
    risk="high",
    handler=lambda request: handle_desktop_action(request)
))

for tool_name, description, handler in (
    ("describe_current_screen", "Capture and describe visible content across the desktop.", describe_current_screen),
    ("describe_active_window", "Capture and describe the active application window.", describe_active_window),
):
    registry.register(ToolSpec(
        name=tool_name,
        description=description,
        input_schema={
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": [],
            "additionalProperties": False,
        },
        risk="low",
        handler=handler,
    ))
