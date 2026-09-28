import json
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    summary: str
    details: str
    changed: bool
    artifact: Optional[str]
    truncated: bool

    def __str__(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)
