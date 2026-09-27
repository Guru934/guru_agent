import os
from pathlib import Path

# Base directories
APP_DIR = Path(__file__).parent.parent.absolute()
USER_STATE_DIR = Path(os.path.expanduser("~/.local/share/guru_agent"))
USER_STATE_DIR.mkdir(parents=True, exist_ok=True)

# Database
DB_PATH = USER_STATE_DIR / "history.db"

# Logs & Status
HANDOFF_STATUS_FILE = APP_DIR / "handoff_status.txt"
HANDOFF_TASKS_FILE = APP_DIR / "handoff_tasks.txt"
