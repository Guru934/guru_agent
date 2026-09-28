import os
from pathlib import Path
from typing import Optional

from config import APP_DIR, WORKSPACE_ROOTS


def resolve_workspace_path(
    path: str, base_dir: Path = APP_DIR, allowed_root: Optional[Path] = None
) -> Path:
    target = Path(os.path.expanduser(path))
    if not target.is_absolute():
        target = base_dir / target
    resolved = target.resolve()
    in_configured_workspace = any(
        resolved == root.resolve() or resolved.is_relative_to(root.resolve())
        for root in WORKSPACE_ROOTS
    )
    in_active_project = False
    if allowed_root is not None:
        active_root = Path(allowed_root).resolve()
        in_active_project = resolved == active_root or resolved.is_relative_to(active_root)
    allowed = in_active_project if allowed_root is not None else in_configured_workspace
    if not allowed:
        raise PermissionError(f"Path {path!r} is outside the allowed workspace roots.")
    return resolved
