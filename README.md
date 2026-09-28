# Guru Agent

A local-first personal desktop AI assistant for Linux (Hyprland/Wayland) that blends:

- **Gemini Live** — Real-time voice conversation with streaming audio
- **AgentRuntime** — Heavy execution agent for complex multi-step tasks (coding, file ops, shell, git)
- **Fast Desktop Actions** — Trusted capabilities: open app/website, volume/brightness, YouTube search
- **Session Memory** — SQLite-backed chat history with voice/text unified pipeline
- **Approval System** — Human-in-the-loop for sensitive actions with capability grants

## Architecture

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
│  │             │  └───────────────────────────────────────┘  │  │
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
│  • Auto-reconnect with exponential backoff                      │
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

## Key Bindings (Hyprland)

| Key | Action |
|-----|--------|
| **F1** | Toggle window visibility |
| **F2** | Wake voice assistant (global, works when hidden) |
| **F3** | Toggle window visibility |
| **F11** | Application fullscreen (Qt) |
| **Super+F** | Compositor fullscreen (Hyprland) |

## Voice Assistant Usage
 
 1. **Start**: Press **F2** (global hotkey, works when window hidden/tiled/fullscreen)
 2. **Speak**: Assistant listens (🔴 Listening indicator)
 3. **Auto-sleep**: After 50s silence or when response completes
 4. **Next command**: Press **F2** again
 
 No push-to-talk button — F2 is a global background hotkey via `/tmp/guru_agent_voice_toggle` file watcher.

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
│   ├── audio.py              # AudioInterface (mic mute event for push-to-talk)
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

## Status Indicators (Top Bar)

- **● Task**: Idle / Running / Waiting Approval / Tool → name
- **● Live**: Disconnected / Connecting / Connected / Error
- **● Voice**: Sleeping / Listening / Thinking / Speaking

## Capability Grants (Trust & Safety Panel)

Parameter-scoped grants created via "Always allow" in approval dialog:
- `open_application` → `app_name="chrome"` only
- `set_volume` → `level_percent` range 0-100
- Persistent (survives restart) or session-scoped with expiry

## Development

```bash
# Run tests (99 passing)
python -m pytest tests/ -q

# Format code
ruff format .

# Type check
ruff check .
```

## Roadmap

- [x] Phase 1: Stabilize Gemini Live lifecycle (state machines, auto-sleep, silent reconnect)
- [x] Phase 2: F2 global wake/sleep (replaced push-to-talk)
- [x] Phase 3: Unified voice/text chat pipeline (single SQLite conversation)
- [x] Phase 4: Real Agent Terminal (EventBus streaming from ToolExecutor)
- [x] Phase 5: Contextual terminal visibility (auto-show for execution tools only)
- [x] Phase 6: Responsive layout (stretch factors, no hardcoded geometry)
- [x] Phase 7: Clean status model (3 independent indicators)
- [x] Phase 8: Fullscreen layers (F11=Qt, Super+F=Hyprland)
- [x] Phase 9: Documentation cleanup (this README, PROJECT_STATUS, update.md)
- [ ] Phase 10: UI redesign (polish after architecture stable)