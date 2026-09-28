#!/bin/bash
# Guru Agent Launcher - toggles visibility or voice if running, otherwise starts the app

set -euo pipefail

AGENT_DIR="/home/guru/guru_agent"
PYTHON="$AGENT_DIR/.venv/bin/python"
APP_SCRIPT="$AGENT_DIR/app.py"
TOGGLE_FILE="/tmp/guru_agent_toggle"
VOICE_TOGGLE_FILE="/tmp/guru_agent_voice_toggle"

# Function to find the Guru Agent process PID
find_agent_pid() {
    pgrep -f "python.*app\.py" | head -1
}

# Function to trigger the watcher file
trigger_toggle() {
    local file=$1
    date +%s%N > "$file"
    return 0
}

main() {
    local cmd="${1:-visibility}"
    local pid=$(find_agent_pid)
    
    if [[ -n "$pid" ]]; then
        if [[ "$cmd" == "voice" ]]; then
            echo "Guru Agent already running (PID: $pid), toggling voice..."
            trigger_toggle "$VOICE_TOGGLE_FILE"
        elif [[ "$cmd" == "visibility-only" ]]; then
            echo "Guru Agent already running (PID: $pid), toggling visibility..."
            trigger_toggle "$TOGGLE_FILE"
        else
            echo "Guru Agent already running (PID: $pid), toggling visibility..."
            trigger_toggle "$TOGGLE_FILE"
        fi
        exit 0
    fi
    
    # Not running
    if [[ "$cmd" == "visibility-only" ]]; then
        # F3: visibility-only - don't start if not running
        echo "Guru Agent not running, visibility-only toggle ignored"
        exit 0
    elif [[ "$cmd" == "voice" ]]; then
        # F2: voice - start agent and toggle voice (WAKE, not toggle)
        echo "Starting Guru Agent for voice..."
        cd "$AGENT_DIR"
        exec "$PYTHON" "$APP_SCRIPT" &
        
        # Wait for agent to be ready by polling for voice toggle file
        # The Qt app creates the voice toggle file watcher on startup
        local max_wait=10
        local waited=0
        while [[ ! -f "$VOICE_TOGGLE_FILE" && $waited -lt $max_wait ]]; do
            sleep 0.5
            waited=$((waited + 1))
        done
        
        if [[ -f "$VOICE_TOGGLE_FILE" ]]; then
            trigger_toggle "$VOICE_TOGGLE_FILE"
        else
            echo "Warning: Voice toggle file not found after ${max_wait}s, triggering anyway"
            trigger_toggle "$VOICE_TOGGLE_FILE"
        fi
    else
        # F1: launch or toggle visibility - start if not running
        echo "Starting Guru Agent..."
        cd "$AGENT_DIR"
        exec "$PYTHON" "$APP_SCRIPT" &
    fi
}

main "$@"
