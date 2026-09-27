import os
from pathlib import Path

from config import APP_DIR, WORKSPACE_ROOTS


def resolve_workspace_path(path: str, base_dir: Path = APP_DIR) -> Path:
    target = Path(os.path.expanduser(path))
    if not target.is_absolute():
        target = base_dir / target
    resolved = target.resolve()
    if not any(
        resolved == root.resolve() or resolved.is_relative_to(root.resolve())
        for root in WORKSPACE_ROOTS
    ):
        raise PermissionError(f"Path {path!r} is outside the allowed workspace roots.")
    return resolved
