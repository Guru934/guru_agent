#!/bin/bash
# Guru Agent Launcher - toggles visibility if running, otherwise starts the app

set -euo pipefail

AGENT_DIR="/home/guru/guru_agent"
APP_NAME="cat-talker-overlay"
PYTHON="$AGENT_DIR/.venv/bin/python"
APP_SCRIPT="$AGENT_DIR/app.py"
TOGGLE_FILE="/tmp/guru_agent_toggle"

# Function to find the Guru Agent process PID
find_agent_pid() {
    # Look for the process running app.py
    pgrep -f "python.*app\.py" | head -1
}

# Function to toggle visibility via toggle file
toggle_visibility() {
    # Write current timestamp to toggle file to trigger visibility toggle
    date +%s%N > "$TOGGLE_FILE"
    return 0
}

main() {
    # Check if agent is already running
    local pid=$(find_agent_pid)
    
    if [[ -n "$pid" ]]; then
        echo "Guru Agent already running (PID: $pid), toggling visibility..."
        toggle_visibility
        exit 0
    fi
    
    # Not running, start it
    echo "Starting Guru Agent..."
    cd "$AGENT_DIR"
    exec "$PYTHON" "$APP_SCRIPT" &
}

main "$@"