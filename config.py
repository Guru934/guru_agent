import os
from pathlib import Path

# Base directories
APP_DIR = Path(__file__).parent.absolute()
USER_STATE_DIR = Path(os.path.expanduser("~/.local/share/guru_agent"))
USER_STATE_DIR.mkdir(parents=True, exist_ok=True)

# Database
DB_PATH = USER_STATE_DIR / "history.db"

# Logs & Status

# Security Sandboxing
WORKSPACE_ROOTS = [
    APP_DIR,
    Path(os.path.expanduser('~/guru_projects')),
    Path(os.path.expanduser('~/.local/share/guru_agent'))
]

# Filesystem Limits
MAX_READ_BYTES = 1_000_000
MAX_WRITE_BYTES = 1_000_000
