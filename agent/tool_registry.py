from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass
from tools.shell import execute_bash_command, ripgrep_search_impl
from tools.filesystem import read_file, write_file_content
from tools.desktop import handle_desktop_action
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
    handler=lambda command: execute_bash_command(command)
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
    handler=lambda path, content: write_file_content(path, content)
))

registry.register(ToolSpec(
    name="read_file",
    description="Reads the contents of a file.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"}
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    risk="low",
    handler=lambda path: read_file(path)
))

registry.register(ToolSpec(
    name="search",
    description="Search files linearly for a query string.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"}
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    risk="low",
    handler=lambda query: ripgrep_search_impl(query)
))

registry.register(ToolSpec(
    name="desktop_action",
    description="Perform a supported desktop action such as opening an application or website, or setting volume or brightness.",
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
