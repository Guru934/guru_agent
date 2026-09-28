# Guru Agent - Master TODO List

**Last Updated:** 2026-09-28
**Session:** All Phases 1-10 Complete
**Branch:** main

---

## Phase Status Overview

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Stabilize Gemini Live lifecycle | ✅ **COMPLETE** |
| Phase 2 | F2 global wake/sleep (replace push-to-talk) | ✅ **COMPLETE** |
| Phase 3 | Unify voice/text chat pipeline | ✅ **COMPLETE** |
| Phase 4 | Real Agent Terminal connected to ToolExecutor | ✅ **COMPLETE** |
| Phase 5 | Contextual terminal visibility | ✅ **COMPLETE** |
| Phase 6 | Responsive/scalable layout - remove hardcoded geometry | ✅ **COMPLETE** |
| Phase 7 | Clean up status model | ✅ **COMPLETE** |
| Phase 8 | Fix fullscreen at correct layer | ✅ **COMPLETE** |
| Phase 9 | Documentation cleanup | ✅ **COMPLETE** |
| Phase 10 | UI redesign | ✅ **COMPLETE** |

---

## Summary of All Fixes

### Phase 1: Gemini Live Lifecycle ✅
- **Independent state machines**: `ConnectionState`, `VoiceState`, `TaskState` as Literal types
- **VoiceStateManager** with 50s inactivity auto-sleep timer (was 8s)
- Context injected via system_instructions (not user turn) — eliminates unsolicited speech
- `wake_voice()` / `sleep_voice()` callable from UI thread
- Callbacks separated: connection, voice, task
- Reconnect is silent — context appended to system_instructions, no user turn

### Phase 2: F2 Global Wake/Sleep ✅
- Replaced push-to-talk button with `[F2] Wake Voice` indicator
- Dual `QFileSystemWatcher` for `/tmp/guru_agent_toggle` (visibility) + `/tmp/guru_agent_voice_toggle` (voice)
- `launch_agent.sh` accepts `voice` parameter → starts agent if needed, then wakes voice
- Auto-sleep on `turn_complete` → `sleeping` (50s inactivity timer)
- F2 works when window hidden/tiled/fullscreen (Hyprland file watcher + Qt keyPressEvent fallback)

### Phase 3: Unified Voice/Text Chat ✅
- Single `_append_conversation_message()` for both voice and text
- Voice transcripts → user bubbles, model responses → assistant bubbles
- Streaming transcripts: single bubble updated in real-time
- `model_turn_complete` signal commits to SQLite
- System events (connection, approval, task) stay as system bubbles, not in conversation DB

### Phase 4: Real Agent Terminal ✅
- `AgentTerminal` transformed from QProcess bash to read-only EventBus stream monitor
- `ToolExecutor` passes `_task_id` via inspect to shell tool
- `execute_bash_command` emits `SHELL_COMMAND`, `SHELL_OUTPUT`, `SHELL_EXIT` events
- Real-time streaming: command (cyan), output (white), exit code (green/red)

### Phase 5: Contextual Terminal Visibility ✅
- Auto-shows ONLY for execution tools: `execute_shell`, `read_file`, `write_file`, `search`, `PythonExec`
- Auto-shows for `APPROVAL_REQUIRED`
- Stays hidden for simple desktop actions (open app, volume, brightness, YouTube)

### Phase 6: Responsive Layout ✅
- Horizontal splitter: Sidebar (stretch=0), Chat (stretch=1)
- Vertical splitter: Chat feed (stretch=1), Terminal drawer (stretch=0)
- Terminal drawer starts collapsed (size 0)
- Input bar pinned to bottom (stretch=0)
- Sidebar toggle → chat expands automatically

### Phase 7: Clean Status Model ✅
- Three clear indicators:
  - `task_state_label`: Task: Idle / Running / Waiting Approval / Tool → name
  - `connection_state_label`: Live: Disconnected / Connecting / Connected / Error
  - `voice_state_label`: Voice: Sleeping / Listening / Thinking / Speaking
- Task success/failure removed from chat feed (only approvals in chat)
- Removed "reconnected" auto-transition spam

### Phase 8: Fullscreen Layers ✅
- Button (⛶) + F11 → Qt application fullscreen (`showFullScreen()`)
- Super+F → Hyprland compositor fullscreen (`hyprctl dispatch fullscreen`)
- Separated `toggle_fullscreen()` from `toggle_compositor_fullscreen()`

### Phase 9: F2/F3 Key Fixes ✅
- **F2**: Voice wake/sleep — auto-starts voice assistant if not running, then wakes
- **F3**: Visibility-only — toggles window without launching agent
- Works via Hyprland (global) + Qt keyPressEvent fallback (when focused)

### Phase 10: UI Redesign ✅
- **Theme**: Darker base (`#121218` sidebar, `#14141b` input), consistent 14px radius, softer borders
- **Bubbles**: User `#253048`/16px radius, Assistant transparent, System bordered, Error red-bordered
- **Terminal**: `#121218` bg, JetBrains Mono 13px, cyan prompt, yellow commands, green/red exit codes
- **Status Indicators**: Dedicated label styles, 600 weight, 12-14px padding, 12-14px radius
- **Code Blocks**: JetBrains Mono 12.5px, 1.5 line-height, subtle border

---

## Key Files Modified

| File | Changes |
|------|---------|
| `providers/gemini_live.py` | Voice state machine, silent reconnect, greeting on connect, 50s auto-sleep |
| `ui/main_window.py` | Layout, status indicators, F2/F3 handlers, shell event handling, voice state UI |
| `ui/widgets.py` | AgentTerminal as EventBus stream monitor, JetBrains Mono font |
| `tools/shell.py` | SHELL_COMMAND/OUTPUT/EXIT event emission |
| `launch_agent.sh` | F1/F3 visibility, F2 voice with auto-start |
| `agent/events.py` | Event bus for shell events |

---

## Test Results

```
99 passed, 1 warning in ~20s
```

---

## Quick Commands

```bash
cd /home/guru/guru_agent
python -m pytest tests/ -q    # Run tests (99 pass)
python app.py                 # Launch app
```

---

## Keybinds (Hyprland)

| Key | Action |
|-----|--------|
| **F1** | Launch or toggle visibility |
| **F2** | Voice wake/sleep (auto-starts voice service) |
| **F3** | Visibility-only toggle (no launch) |
| **F11** | Qt application fullscreen |
| **Super+F** | Hyprland compositor fullscreen |