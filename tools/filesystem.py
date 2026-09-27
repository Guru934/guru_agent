import os

from tools.workspace import resolve_workspace_path


def read_file(path: str) -> str:
    file_path = resolve_workspace_path(path)
    descriptor = os.open(file_path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "r", encoding="utf-8") as source:
        return source.read()

def write_file_content(path: str, content: str) -> str:
    target = resolve_workspace_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target = resolve_workspace_path(path)
    descriptor = os.open(
        target,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
        0o666,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
        destination.write(content)
    return f"Wrote file: {target}"
