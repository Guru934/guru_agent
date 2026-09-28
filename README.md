# Guru Agent

A **local-first personal desktop AI assistant** for Linux (Hyprland/Wayland) that seamlessly blends real-time voice conversation with powerful agentic execution capabilities.

## What This Project Is About

Guru Agent is a desktop AI assistant designed to be your always-available companion on Linux. It combines:

- **Real-time voice conversation** via Google Gemini Live API — natural, streaming voice interaction with <500ms latency
- **Agentic execution** via a local AgentRuntime — complex multi-step tasks (coding, file operations, shell commands, git, browser automation)
- **Fast desktop actions** — Trusted capabilities for instant desktop control (open apps, set volume/brightness, search YouTube)
- **Persistent memory** — SQLite-backed conversation history with unified voice/text pipeline
- **Security-first design** — Human-in-the-loop approval system with parameter-scoped capability grants
- **Hyprland/Wayland native** — Global hotkeys, compositor integration, proper tiling window behavior

### Core Philosophy

1. **Local-first** — Heavy execution runs locally via Ollama; only voice conversation uses cloud Gemini
2. **Voice-native** — F2 global hotkey wakes assistant; natural conversation flow with 50s auto-sleep
3. **Security boundary** — Single ToolExecutor + PolicyEngine + ApprovalManager; capability grants never bypass security
4. **Two execution paths** — Fast trusted capabilities (instant) vs Heavy AgentRuntime (complex tasks)
5. **Privacy-aware** — Voice conversation is cloud; execution is local; system messages never persist to conversation DB

---

## What We've Built (Complete Phases 1-9)

### Phase 1: Gemini Live Lifecycle Stabilization ✅
- Independent state machines: `ConnectionState`, `VoiceState`, `TaskState` (Literal types)
- `VoiceStateManager` with 50s inactivity auto-sleep timer
- Context injected via `system_instructions` (silent, no user turns)
- `wake_voice()` / `sleep_voice()` callable from UI thread
- Callbacks separated: connection, voice, task (no cross-coupling)
- Silent reconnect: no chat messages, no greeting, 10-attempt ceiling with error state

### Phase 2: F2 Global Wake/Sleep ✅
- Replaced push-to-talk button with `[F2] Wake Voice` indicator
- Dual `QFileSystemWatcher`: `/tmp/guru_agent_toggle` (visibility) + `/tmp/guru_agent_voice_toggle` (voice)
- `launch_agent.sh` accepts `voice` parameter → starts agent if needed, then wakes
- Auto-sleep on `turn_complete` → `sleeping` (50s inactivity timer)
- F2 works when window hidden/tiled/fullscreen (Hyprland file watcher + Qt keyPressEvent fallback)

### Phase 3: Unified Voice/Text Chat Pipeline ✅
- Single `_append_conversation_message()` for both voice and text
- Voice transcripts → user bubbles; model responses → assistant bubbles
- Streaming transcripts: single bubble updated in real-time
- `model_turn_complete` signal commits to SQLite
- System events (connection, approval, task) stay as system bubbles, not in conversation DB

### Phase 4: Real Agent Terminal (EventBus Streaming) ✅
- `AgentTerminal` transformed from QProcess bash to read-only EventBus stream monitor
- `ToolExecutor` passes `_task_id` via `inspect` to shell tool
- `execute_bash_command` emits `SHELL_COMMAND`, `SHELL_OUTPUT`, `SHELL_EXIT` events
- Real-time streaming: command (cyan), output (white), exit code (green/red)

### Phase 5: Contextual Terminal Visibility ✅
- Auto-shows ONLY for execution tools: `execute_shell`, `read_file`, `write_file`, `search`, `PythonExec`
- Auto-shows for `APPROVAL_REQUIRED`
- Stays hidden for simple desktop actions (open app, volume, brightness, YouTube)

### Phase 6: Responsive/Scalable Layout ✅
- Horizontal splitter: Sidebar (stretch=0), Chat (stretch=1)
- Vertical splitter: Chat feed (stretch=1), Terminal drawer (stretch=0)
- Terminal drawer starts collapsed (size 0)
- Input bar pinned to bottom (stretch=0)
- Sidebar toggle → chat expands automatically

### Phase 7: Clean Status Model ✅
- Three independent indicators:
  - `task_state_label`: Task: Idle / Running / Waiting Approval / Tool → name
  - `connection_state_label`: Live: Disconnected / Connecting / Connected / Error
  - `voice_state_label`: Voice: Sleeping / Listening / Thinking / Speaking
- Task success/failure removed from chat feed (only approvals in chat)
- Removed "reconnected" auto-transition spam

### Phase 8: Fullscreen Layers ✅
- Button (⛶) + F11 → Qt application fullscreen (`showFullScreen()`)
- Super+F → Hyprland compositor fullscreen (`hyprctl dispatch fullscreen`)
- Separated `toggle_fullscreen()` from `toggle_compositor_fullscreen()`

### Phase 9: Documentation & Cleanup ✅
- F2/F3 key fixes: Voice auto-starts on F2, F3 visibility-only
- Documentation updated: 8s→50s in README, PROJECT_STATUS
- Removed `hello.py` artifact
- Push-to-talk remnants removed

---

## Current Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER (F2 Voice / Text)                   │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  ScratchpadWindow (Qt)                                          │
│  ┌─────────────┬─────────────────────────────────────────────┐  │
│  │  Sidebar    │  Chat Area                                  │  │
│  │  Sessions   │  ┌───────────────────────────────────────┐  │  │
│  │  Trust&Safe │  │ Chat Feed (user/assistant bubbles)    │  │  │
│  │             │  ├───────────────────────────────────────┤  │  │
│  │             │  │ Agent Terminal (EventBus streaming)   │  │  │
│  │             │  │ • SHELL_COMMAND/OUTPUT/EXIT events    │  │  │
│  │             │  │ • Auto-shows for execution tools      │  │  │
│  │             │  ├───────────────────────────────────────┤  │  │
│  │             │  │ Input Bar [F2] Wake Voice | 📸 | 🪟 | ➤ │  │  │
│  └─────────────┴─────────────────────────────────────────────┘  │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Gemini Live (Conversation Model)                               │
│  • Voice: Sleeping → Listening → Thinking → Speaking → Sleeping │
│  • Delegation tools: delegate_to_agent, get_agent_status,       │
│    approve_pending_action, reject_pending_action,               │
│    get_project_context, get_task_history, find_task_by_description │
│  • Context injected via system_instructions (no user turns)     │
│  • Auto-reconnect with exponential backoff (10-attempt ceiling) │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  AssistantBridge (Coordination Layer)                           │
│  • Task delegation → AgentRuntime (background thread)           │
│  • EventBus → AssistantEvent → Gemini Live + UI                 │
│  • Approval tracking, capability grants, project context        │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  AgentRuntime (Execution Model)                                 │
│  • ToolExecutor + PolicyEngine + ApprovalManager                │
│  • Desktop tools (6 granular), Shell, Files, Browser, Vision    │
│  • Real-time EventBus streaming to Agent Terminal               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Security Model

### Single Security Boundary
```
ToolExecutor + PolicyEngine + ApprovalManager + CapabilityGrants
```

### Two Execution Paths

| Path | Tools | Speed | Approval |
|------|-------|-------|----------|
| **Fast** | `open_application`, `open_website`, `set_volume`, `set_brightness`, `get_clipboard`, `search_and_play_youtube` | Instant | Capability grants (parameter-scoped) |
| **Heavy** | `execute_shell`, `read_file`, `write_file`, `search`, `PythonExec`, browser, vision | Async | Full PolicyEngine + ApprovalManager |

### Capability Grants
- Parameter-scoped (e.g., `open_application` → `app_name="chrome"` only)
- Range constraints (e.g., `set_volume` → `level_percent` 0-100)
- Persistent (survives restart) or session-scoped with expiry
- Never bypass ToolExecutor — only change `requires_approval=True` → `False`

### Approval System
- Human-in-the-loop for sensitive actions
- Approval timeout (300s default), cancellable
- "Always allow" creates persistent CapabilityGrant with exact constraints
- Voice approval ONLY resolves existing approvals — cannot create new actions

---

## Project Structure

```
guru_agent/
├── app.py                    # Entry point, QApplication setup
├── launch_agent.sh           # F1/F3 visibility + F2 voice toggle launcher
├── requirements.txt
├── .env                      # GEMINI_API_KEY, HEAVY_AGENT_MODEL
├── update.md                 # Complete phase-by-phase changelog
├── TODO.md                   # Master task list
├── ui/
│   ├── main_window.py        # ScratchpadWindow (main UI)
│   ├── widgets.py            # AgentTerminal, MessageBubble, Visualizers
│   ├── audio.py              # AudioInterface (mic mute event for voice wake/sleep)
│   └── approval_dialog.py    # Approval UI with "Always allow" grants
├── providers/
│   └── gemini_live.py        # Gemini Live API, VoiceStateManager, state machines
├── agent/
│   ├── runtime.py            # AgentRuntime (execution model)
│   ├── executor.py           # ToolExecutor + PolicyEngine + ApprovalManager
│   ├── assistant_bridge.py   # Coordination layer (delegation, context, approvals)
│   ├── assistant_events.py   # AssistantEvent dataclass
│   ├── capabilities.py       # CapabilityRegistry, CapabilityGrant
│   ├── policy.py             # PolicyEngine with capability grant integration
│   ├── approvals.py          # ApprovalManager (timeout, cancellable)
│   └── tool_registry.py      # Tool definitions with strict schemas
├── tools/
│   ├── desktop.py            # 6 granular desktop capabilities
│   ├── shell.py              # execute_bash_command with EventBus streaming
│   ├── filesystem.py         # File ops with workspace limits
│   └── vision.py             # Screen/window capture
└── memory/
    └── sqlite.py             # Sessions, messages, capability grants
```

---

## Key Bindings (Hyprland)

| Key | Action | Implementation |
|-----|--------|----------------|
| **F1** | Launch/toggle window visibility | `launch_agent.sh` → file watcher |
| **F2** | Voice wake/sleep (global, auto-starts service) | `launch_agent.sh voice` → file watcher + Qt fallback |
| **F3** | Visibility-only toggle (no launch) | `launch_agent.sh visibility-only` → file watcher + Qt fallback |
| **F11** | Qt application fullscreen | `toggle_fullscreen()` |
| **Super+F** | Hyprland compositor fullscreen | `hyprctl dispatch fullscreen` |

---

## Voice Assistant Usage

1. **Start**: Press **F2** (global hotkey, works when window hidden/tiled/fullscreen)
2. **Speak**: Assistant listens (🔴 Listening indicator)
3. **Auto-sleep**: After 50s silence or when response completes
3. **Next command**: Press **F2** again

No push-to-talk button — F2 is a global background hotkey via `/tmp/guru_agent_voice_toggle` file watcher.

**Voice Assistant Button** (top bar):
- Click → Starts Gemini Live, connects, speaks greeting, enters LISTENING
- Click again → Stops voice assistant completely

---

## Voice State Machine

```
           ┌────────────┐
           │  SLEEPING  │
           └─────┬──────┘
                 │ F2 / Voice Assistant ON
                 ▼
           ┌────────────┐
           │ LISTENING  │ ◄──────────────────────┐
           └─────┬──────┘                        │
                 │ User speaks                   │ 50s inactivity
                 ▼                               │
           ┌────────────┐                        │
           │ THINKING   │                        │
           └─────┬──────┘                        │
                 │ Model responds                │
                 ▼                               │
           ┌────────────┐                        │
           │ SPEAKING   │                        │
           └─────┬──────┘                        │
                 │ Audio finishes                │
                 ▼                               │
           ┌────────────┐                        │
           │ LISTENING  │ ──────────────────────┘
           └────────────┘
                 │ 50s no user speech
                 ▼
           ┌────────────┐
           │  SLEEPING  │
           └────────────┘
```

---

## Quick Start

```bash
# 1. Install dependencies
python -m pip install -r requirements.txt

# 2. Start Ollama and pull a model (for heavy execution)
ollama pull qwen2.5-coder

# 3. Configure environment
cp .env.example .env
# Edit .env: set GEMINI_API_KEY, HEAVY_AGENT_MODEL=qwen2.5-coder

# 4. Run
python app.py
```

### Requirements
- **Python 3.12+**
- **Hyprland/Wayland** (for global hotkeys and compositor integration)
- **Ollama** running locally with a model (e.g., `qwen2.5-coder`)
- **Gemini API Key** (for voice conversation)
- **PulseAudio/PipeWire** (for audio I/O)
- **Dependencies**: `PyQt6`, `google-genai`, `pyaudio`, `numpy`, `ruff`, `pytest`

---

## Environment Variables (`.env`)

```env
# Required
GEMINI_API_KEY=your_gemini_api_key_here

# Required for heavy execution
HEAVY_AGENT_MODEL=qwen2.5-coder  # or any Ollama model

# Optional
WORKSPACE_ROOT=/home/guru/guru_agent  # Workspace root for file tools
SAFE_MODE=true  # Disable file writes/shell commands without approval
```

---

## Development

```bash
# Run tests (99 passing)
python -m pytest tests/ -q

# Format code
ruff format .

# Type check
ruff check .

# Run application
python app.py

# Launch via Hyprland keybinds (see launch_agent.sh)
```

---

## Test Coverage (99 Tests Passing)

| Category | Tests |
|----------|-------|
| Core Evals | 11 |
| Fast Actions | 8 |
| Orchestrator | 4 |
| Agent Hardening | 32 |
| Assistant Features | 12 |
| Capability Grants | 8 |
| Phase 10 Recovery | 4 |
| Voice/Assistant Integration | 12 |
| **Total** | **99** |

---

## What's Left To Do (Phase 10+)

### Phase 10: UI Redesign (Polish)
- [ ] Visual consistency & theming refinements
- [ ] Smooth animations (terminal drawer, sidebar, bubbles)
- [ ] Accessibility improvements (focus management, keyboard nav, screen reader)
- [ ] Empty states & onboarding flow
- [ ] Responsive breakpoints refinement
- [ ] Dark/light theme support (if needed)

### Phase 11: Advanced Voice Features
- [ ] Voice activity detection (VAD) for more natural turn-taking
- [ ] Interruption handling (user speaks while assistant speaking)
- [ ] Multi-language support
- [ ] Voice profiles / speaker recognition

### Phase 12: Agent Capabilities Expansion
- [ ] Git integration (diff, commit, branch management)
- [ ] Docker/container management
- [ ] Package manager integration (pip, npm, cargo, apt)
- [ ] Database tools (SQL query, migration)
- [ ] API testing tools (REST/GraphQL)

### Phase 13: Collaboration & Sync
- [ ] Multi-device session sync
- [ ] Shared workspaces
- [ ] Conversation export/import (JSON, Markdown)

### Phase 14: Plugin System
- [ ] Plugin API for custom tools
- [ ] Community plugin marketplace
- [ ] Sandboxed plugin execution

### Phase 15: Mobile/Remote Access
- [ ] Web UI companion
- [ ] Mobile app (Flutter/React Native)
- [ ] Remote voice wake via push notification

---

## Known Issues / Limitations

1. **Gemini Live SDK** — Occasional connection drops; exponential backoff handles most cases
2. **Audio on Wayland** — Requires PulseAudio/PipeWire; `qt.qpa.services` portal warning is cosmetic
3. **Hyprland keybinds** — Must be configured in user's `hyprland.conf` (not in repo)
4. **Microphone permissions** — First run may need `pavucontrol` to select input device
5. **Ollama model** — Heavy execution quality depends on local model choice

---

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Run tests (`python -m pytest tests/ -q`)
4. Format code (`ruff format .`)
5. Type check (`ruff check .`)
6. Submit PR with clear description

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- **Google Gemini Live API** — Real-time voice conversation
- **Ollama** — Local LLM execution
- **PyQt6** — Cross-platform desktop framework
- **Hyprland** — Wayland compositor with excellent IPC
- **ruff** — Fast Python linting/formatting

---

*Built with ❤️ for the Linux desktop. Made to be your daily driver AI companion.*