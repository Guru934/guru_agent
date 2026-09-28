import os
from typing import Optional

from config import APP_DIR, MAX_READ_BYTES, MAX_WRITE_BYTES
from tools.workspace import resolve_workspace_path


def read_file(
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    _workspace_dir=None,
) -> str:
    file_path = resolve_workspace_path(path, base_dir=_workspace_dir or APP_DIR, allowed_root=_workspace_dir)
    file_size = file_path.stat().st_size
    if file_size > MAX_READ_BYTES:
        raise ValueError(f"File size ({file_size} bytes) exceeds maximum read limit ({MAX_READ_BYTES} bytes).")
    descriptor = os.open(file_path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "r", encoding="utf-8") as source:
        content = source.read()
    if len(content.encode("utf-8")) > MAX_READ_BYTES:
        raise ValueError(f"File content size exceeds maximum read limit ({MAX_READ_BYTES} bytes).")
    if start_line is not None or end_line is not None:
        for value, label in ((start_line, "start_line"), (end_line, "end_line")):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
                raise ValueError(f"{label} must be a 1-based positive line number.")
        lines = content.splitlines(keepends=True)
        start = start_line if start_line is not None else 1
        end = end_line if end_line is not None else len(lines)
        if start > end:
            raise ValueError("start_line must be less than or equal to end_line.")
        if start > len(lines) or end > len(lines):
            raise ValueError(f"Requested line range exceeds file length ({len(lines)} lines).")
        content = "".join(lines[start - 1:end])
    return content


def write_file_content(path: str, content: str, _workspace_dir=None) -> str:
    target = resolve_workspace_path(path, base_dir=_workspace_dir or APP_DIR, allowed_root=_workspace_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target = resolve_workspace_path(path, base_dir=_workspace_dir or APP_DIR, allowed_root=_workspace_dir)
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > MAX_WRITE_BYTES:
        raise ValueError(f"Content size ({len(content_bytes)} bytes) exceeds maximum write limit ({MAX_WRITE_BYTES} bytes).")
    descriptor = os.open(
        target,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
        0o666,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
        destination.write(content)
    return f"Wrote file: {target}"
