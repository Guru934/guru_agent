import os

from config import MAX_READ_BYTES, MAX_WRITE_BYTES
from tools.workspace import resolve_workspace_path


def read_file(path: str) -> str:
    file_path = resolve_workspace_path(path)
    file_size = file_path.stat().st_size
    if file_size > MAX_READ_BYTES:
        raise ValueError(f"File size ({file_size} bytes) exceeds maximum read limit ({MAX_READ_BYTES} bytes).")
    descriptor = os.open(file_path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "r", encoding="utf-8") as source:
        content = source.read()
    if len(content.encode("utf-8")) > MAX_READ_BYTES:
        raise ValueError(f"File content size exceeds maximum read limit ({MAX_READ_BYTES} bytes).")
    return content


def write_file_content(path: str, content: str) -> str:
    target = resolve_workspace_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target = resolve_workspace_path(path)
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
