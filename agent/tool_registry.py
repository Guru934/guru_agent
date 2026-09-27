from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass
from tools.shell import execute_bash_command, ripgrep_search_impl
from tools.filesystem import read_file, write_file_content

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

registry = Registry()

registry.register(ToolSpec(
    name="execute_shell",
    description="Executes a bash/terminal command and returns output.",
    input_schema={
        "type": "OBJECT",
        "properties": {
            "command": {"type": "STRING"}
        },
        "required": ["command"]
    },
    risk="high",
    handler=lambda command: execute_bash_command(command)
))

registry.register(ToolSpec(
    name="write_file",
    description="Writes content to a specific file path.",
    input_schema={
        "type": "OBJECT",
        "properties": {
            "path": {"type": "STRING"},
            "content": {"type": "STRING"}
        },
        "required": ["path", "content"]
    },
    risk="medium",
    handler=lambda path, content: write_file_content(path, content)
))

registry.register(ToolSpec(
    name="read_file",
    description="Reads the contents of a file.",
    input_schema={
        "type": "OBJECT",
        "properties": {
            "path": {"type": "STRING"}
        },
        "required": ["path"]
    },
    risk="low",
    handler=lambda path: read_file(path)
))

registry.register(ToolSpec(
    name="search",
    description="Search files linearly for a query string.",
    input_schema={
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING"}
        },
        "required": ["query"]
    },
    risk="low",
    handler=lambda query: ripgrep_search_impl(query)
))
