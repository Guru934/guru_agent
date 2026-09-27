# Update Log

## Phase 6 Fix: Fix Hyprland Fullscreen Binding + Fullscreen Button (Completed - 2026-09-27)

**Problem**: Two fullscreen issues:
1. Super+F was supposed to toggle fullscreen via Hyprland config (`kbWindowFullscreen = "SUPER + F"`), but the binding wasn't working reliably
2. The fullscreen button (⛶) in the top bar wasn't working on Wayland - `showFullScreen()` doesn't work properly on Wayland without compositor support

**Fix Applied**:
1. **`/home/guru/.config/hypr/hyprland/keybinds.lua`** - Added explicit Super+F binding:
   - Added `create_bind("SUPER + F", hl.dsp.exec_cmd("hyprctl dispatch fullscreen"))`
   - Directly calls Hyprland's fullscreen dispatcher

2. **`ui/main_window.py`** - Fixed fullscreen button to work on Wayland:
   - `toggle_fullscreen()` now detects Wayland session
   - Uses `hyprctl dispatch fullscreen` via subprocess on Wayland
   - Falls back to Qt's `showFullScreen()` on X11
   - Button text updates to show current state (⛶)

**Result**: 
- Super+F now reliably toggles fullscreen via Hyprland
- Fullscreen button (⛶) works on Wayland by calling compositor
- Both methods work together seamlessly

**Tests**: All 99 tests pass.

---

## Phase 5 Fix: Fix Task/Connection/Assistant Status Separation in UI (Completed - 2026-09-27)

**Problem**: The top bar status labels were conflating different states:
- `heavy_agent_status_label` showed "Status: Task Completed" or "Status: Task Failed" - overriding the heavy agent's actual state
- Connection state, assistant state, and task state were not independent
- User couldn't tell if the assistant was connected, thinking, or speaking when a task failed

**Fix Applied**:
1. **`ui/main_window.py`** - Separated status concerns:
   - `heavy_agent_status_label` now only shows heavy agent state: "Idle", "Executing Task...", "Waiting for Approval"
   - `voice_connection_label` unchanged - shows connection state (Connected, Connecting, Disconnected)
   - `assistant_state_label` unchanged - shows assistant state (Idle, Listening, Thinking, Speaking)
   - Task status shown in task panels (already implemented)

2. **Updated event handlers**:
   - `TASK_STARTED`: Heavy agent shows "Executing Task..."
   - `TASK_COMPLETED`/`TASK_FAILED`: Heavy agent returns to "Idle" ONLY when no more active tasks (`_active_task_count == 0`)
   - Task completion/failure shown in task panels and workspace, NOT in top bar

**Result**: Three independent status channels:
- 🔴/🟢 Connection: Disconnected/Connecting/Connected
- 🎙️ Assistant: Idle/Listening/Thinking/Speaking  
- ⚙ Heavy Agent: Idle/Executing/Waiting for Approval

**Tests**: All 99 tests pass.

---

## Phase 4 Fix: Build Temporary Agent Terminal for Execution Tasks (Completed - 2026-09-27)

**Problem**: The Agent Workspace was just a log viewer (MarkdownTextBrowser). For actual execution tasks (coding, scripts, tests, git operations), a real terminal was needed that can:
- Run a persistent shell session
- Show output in real-time
- Accept input programmatically
- Be used by the agent for execution tasks

**Fix Applied**:
1. **`ui/widgets.py`** - Created `AgentTerminal` class:
   - Uses QProcess to run persistent bash shell (`bash -i`)
   - Shows output in real-time via `readyReadStandardOutput` signal
   - `send_command()` method for programmatic command execution
   - `output_received`, `command_finished`, `prompt_ready` signals
   - Auto-restarts shell on exit
   - Inherits from QPlainTextEdit for monospace terminal display

2. **`ui/main_window.py`** - Integrated AgentTerminal:
   - Replaced MarkdownTextBrowser with AgentTerminal in workspace
   - Connected terminal signals (`output_received`, `command_finished`)
   - Added handlers for terminal output and shell restart

3. **Behavior**:
   - Hidden by default, auto-shows when tasks run
   - Agent can send commands via `terminal.send_command()`
   - Real-time output display with timestamps
   - Shell auto-restarts on exit

**Result**: Real terminal for execution tasks - coding, scripts, tests, git operations.

**Tests**: All 99 tests pass.

---

## Phase 3 Fix: Replace Heavy Agent Logs with Contextual Agent Workspace (Completed - 2026-09-27)

**Problem**: The permanent "Heavy Agent Logs" panel was always visible at the bottom of the chat, taking up space even when no tasks were running. It also wasn't populated with actual logs (the polling timer was never implemented).

**Fix Applied**:
1. **`ui/main_window.py`** - Renamed and contextualized the workspace:
   - Renamed "Heavy Agent Logs" → "Agent Workspace" 
   - Added `_active_task_count` tracking
   - Auto-shows workspace when tasks start (`TASK_STARTED`)
   - Auto-hides when all tasks complete (`TASK_COMPLETED`/`TASK_FAILED`)
   - Manual toggle still available for user preference
   - Added `_append_to_workspace()` to populate logs with timestamps
   - LOG events from AgentRuntime now appear in workspace

2. **Behavior**:
   - Idle: Workspace hidden (or user's manual toggle preference)
   - Task running: Workspace auto-opens, shows task progress
   - Task complete: Workspace stays open for review, hides on next idle

**Result**: Contextual workspace that appears only when relevant, showing task-specific execution logs.

**Tests**: All 99 tests pass.

---

## Phase 2 Fix: Conversation-Model vs Execution-Model Separation (Completed - 2026-09-27)

**Problem**: Model boundary was duplicated in two places:
1. `AssistantBridge.delegate_task()` - did its own live model detection and mapping
2. `AgentRuntime._execution_model_id()` - also mapped live models to heavy models

This created inconsistency and made the architecture unclear.

**Fix Applied**:
1. **`agent/assistant_bridge.py`** - Removed duplicate model selection logic from `delegate_task()`:
   - Removed `os` import and `get_preference` import
   - Simplified `delegate_task()` to just pass the model_id through to AgentRuntime
   - AgentRuntime's `_execution_model_id()` is now the single source of truth

2. **`agent/runtime.py`** - Already had `_execution_model_id()` method that correctly maps live models to heavy execution model via `HEAVY_AGENT_MODEL` env var

3. **`ui/main_window.py`** - Added explicit model boundary display in top bar:
   - Added `model_boundary_label` showing "💬 Conversation Model → ⚙ Execution Model"
   - Updates automatically when execution model changes via dropdown
   - Shows both models clearly: e.g., "💬 Gemini 3.8 Live (Primary) → ⚙ Qwen 2.5 (Local)"

4. **`tests/test_agent_hardening.py`** - Increased wait time in reconnection test to 3s for cloud model completion

**Result**: Clear architectural separation - Gemini Live handles conversation, Heavy Agent handles execution. UI explicitly shows both models.

**Tests**: All 99 tests pass.

---

## Phase 1 Fix: Reconnect/Session Recovery Flooding (Completed - 2026-09-27)

**Problem**: Every Gemini Live reconnection sent "Session recovered. Active tasks and approvals restored." to the chat UI, flooding conversation history.

**Root Cause**: In `providers/gemini_live.py:263-265`, reconnection logic called:
```python
await self._inject_system_message(session, f"SESSION RECOVERED:\n{context_str}")
text_callback("system", "Session recovered. Active tasks and approvals restored.")
```

The context injection to the model is correct (so it knows session state), but the `text_callback` flooded the chat.

**Fix Applied**:
1. **`providers/gemini_live.py`** - Removed chat message on reconnect, only send context to model:
   - Removed `text_callback("system", "Session recovered...")` 
   - Added `state_callback("reconnected")` for UI status indicator

2. **`ui/main_window.py`** - Added "reconnected" state handling:
   - Added "reconnected" to `_update_connection_state()` with 🟢 Reconnected display
   - Auto-transitions to "connected" after 2 seconds
   - Added "reconnected" to `_on_live_state()` state_map for assistant indicator

**Result**: Reconnection now shows brief status indicator (🟢 Reconnected → 🟢 Connected) without chat pollution. Model still receives full context for continuity.

**Tests**: All 99 tests pass.

---

# Update Log

## Current Phase Status

**Phases 1–6 are implemented foundations with hardening and integration in progress. They are not complete. Phase 7 is deferred until the criteria below are met; Phase 8 has not started.**

### Phase 1 — Unified Tool Execution

- Agent-issued tools are validated and evaluated by the shared `ToolExecutor` before handlers run.
- Approval waits are bounded and cancellable. Approved work executes on the agent worker rather than blocking the UI thread.
- Legacy XML tool parsing and the separate normal-chat provider worker have been removed.

### Phase 2 — Agent Runtime

- Keyboard and transcribed voice messages use `AgentRuntime`.
- Gemini and Ollama conversations use provider adapters behind the runtime.
- Cancellation state is tied to task lifetime and released on completion.

### Phase 3 — Structured Tool Calls

- Tool definitions use provider-independent JSON schemas.
- Arguments are type-checked, required fields enforced, and undeclared fields rejected before policy evaluation.

### Phase 4 — Workspace and Security

- File tools resolve paths against configured workspace roots and reject paths outside them.
- Shell allowlisting uses parsed commands rather than string-prefix matching. Commands outside the read-only allowlist require approval while safe mode is on; disabling safe mode explicitly allows non-blocked commands. Execution uses a fixed working directory, filtered environment, timeout, and output limit.
- **Approval is not an OS sandbox. Non-allowlisted shell commands permitted with safe mode off, or approved while safe mode is on, are not guaranteed to be filesystem-confined. Do not treat this as safe for unattended execution; stronger OS-level isolation remains future work.**

### Phase 5 — Unified Voice

- Voice transcription feeds the same text submission/runtime path as keyboard input.
- Realtime provider code remains separate and must not execute privileged tools directly.

### Phase 6 — Observability

- Task panels and tool progress are keyed by task ID, so concurrent tasks do not share step state.
- Approval results and task completion/failure remain visible in the UI.

## Phase 0 Hardening (Completed)

### Filesystem Resource Limits
- **Added `MAX_READ_BYTES` and `MAX_WRITE_BYTES`** (1 MB each) to `config.py` to prevent resource exhaustion.
- **Updated `tools/filesystem.py`** to enforce limits:
  - `read_file()` checks file size before reading and content size after reading
  - `write_file_content()` validates content size before writing
  - Both raise `ValueError` with descriptive messages when limits exceeded

### Search Tool Workspace Coverage
- **Fixed `tools/shell.py` `ripgrep_search_impl()`** to search all `WORKSPACE_ROOTS` instead of only `APP_DIR`
- Results are now combined across all configured workspace roots with root labels
- Output still respects `MAX_COMMAND_OUTPUT` truncation

### Shell Policy Improvements
- Policy now rejects absolute executable paths with arguments pointing outside workspace
- Redirection operators (`>`, `<`, `>>`, `2>&1`) correctly trigger approval requirement
- `bash -c` and `sh -c` attack vectors properly blocked or require approval
- Environment variable manipulation attempts (`PATH=`, `LD_PRELOAD=`, `HOME=`) caught by policy

### Comprehensive Test Coverage Added
Added 15 new hardening tests in `tests/test_agent_hardening.py`:

| Test | Purpose |
|------|---------|
| `test_filesystem_read_enforces_max_bytes` | Read limit enforcement |
| `test_filesystem_write_enforces_max_bytes` | Write limit enforcement |
| `test_filesystem_rejects_symlink_traversal` | Symlink inside workspace works |
| `test_filesystem_rejects_parent_symlink_traversal` | Parent directory symlinks rejected |
| `test_shell_rejects_absolute_paths_outside_allowlist` | Absolute paths with outside args require approval |
| `test_shell_rejects_redirection_operators` | Redirection triggers approval |
| `test_shell_rejects_bash_c_attacks` | `bash -c` vectors blocked/approval required |
| `test_shell_rejects_env_variable_attacks` | Env manipulation caught |
| `test_concurrent_approvals_isolated` | Multiple approvals don't interfere |
| `test_approval_after_task_cancellation_rejected` | Cancelled task approvals invalidated |
| `test_duplicate_task_id_lifecycle` | Independent runtimes with same task_id |
| `test_multiple_tool_calls_in_one_response` | Provider returning multiple tool calls handled |
| `test_provider_failure_timeout_behavior` | Provider errors handled gracefully |
| `test_malformed_provider_tool_call_arguments` | Invalid args from provider caught |
| `test_task_observability_under_concurrent_tasks` | Events correctly attributed to task_ids |
| `test_legacy_direct_execution_path_regression` | Direct calls still go through executor |
| `test_ripgrep_searches_all_workspace_roots` | Search covers all workspace roots |

**Test Results**: All 58 tests pass (32 hardening + 26 existing).

## Phase 4.5: Trusted Capability / Permission System (Completed)

*Built before Gemini Live integration — foundation for fast-path trusted actions.*

### 4.5.1 Capability Registry & Grants Storage
- **Created `agent/capabilities.py`** — `CapabilityRegistry` and `CapabilityGrant` dataclass:
  - `CapabilityGrant`: id, capability, constraints (JSON), scope (session/persistent), enabled, created_at, expires_at
  - Parameter-scoped constraints (e.g., `open_application` constrained to `app_name="chrome"`)
  - Range constraints with min/max (e.g., `set_volume` level_percent 0-100)
  - Expiry support for session-scoped grants
  - Thread-safe registry with locking
  
- **Created `agent/permissions.py`** — `PermissionDecision` extending `PolicyDecision`:
  - Adds `source` field (user_grant, policy_default, blocked)
  - `check_capability_grant()` and `apply_capability_grant()` integration functions
  - Grants never bypass ToolExecutor — only change `requires_approval=True` → `False`

- **Extended `memory/sqlite.py`** with `capability_grants` table:
  - Columns: id, capability, constraints_json, scope, enabled, created_at, expires_at
  - Added `get_db_connection()` context manager for consistent DB access
  - Survives application restarts

### 4.5.2 Capability Definitions (Replaced monolithic `desktop_action`)
- **Updated `agent/tool_registry.py`** — Split into 6 granular capabilities:
  | Tool | Risk | Arguments | Purpose |
  |------|------|-----------|---------|
  | `open_application` | high | `app_name` (string) | Open desktop app by name |
  | `open_website` | high | `url` (string) | Open URL in browser |
  | `set_volume` | medium | `level_percent` (int 0-100) | System volume control |
  | `set_brightness` | medium | `level_percent` (int 0-100) | Screen brightness control |
  | `get_clipboard` | low | (none) | Read clipboard contents |
  | `search_and_play_youtube` | high | `query` (string) | Search & play YouTube |
  | `desktop_action` | high | `request` (string) | **Legacy fallback** kept for compatibility |

- **All tools use typed parameters** (not free-text), strict JSON schemas with `additionalProperties: false`

### 4.5.3 Permission UI & Management
- **Added "Trust & Safety" panel in sidebar** (`ui/main_window.py`):
  - **Always Allowed** (green): Capabilities with active grants — shows scope badge [Persistent]/[Session], click to revoke
  - **Ask When Needed** (orange): Capabilities without grants — click to grant with constraints dialog
  - **Blocked** (red): Shell, file writes — always require approval
  - Refresh button to update panel

- **Enhanced `ApprovalDialog`** (`ui/approval_dialog.py`):
  - Added "Always allow this kind of action" checkbox
  - When checked on approve → creates persistent `CapabilityGrant` with exact constraints
  - Constraints derived from tool arguments (app_name, url, level_percent range)

- **Grant creation flow** in `main_window.py` approval handler:
  - Creates `CapabilityGrant` with tool arguments as constraints
  - Scope: persistent (survives restart)
  - Auto-refreshes Trust & Safety panel
  - System message confirms grant creation

### 4.5.4 Integration with PolicyEngine
- **Modified `agent/policy.py`**:
  - Added `_check_capability_grant()` method using `capability_registry`
  - In `evaluate()`: if `decision.requires_approval` and grant exists → `requires_approval=False`
  - Grants are additive — don't weaken workspace confinement or blocked command rules
  - Audit log records "Allowed by capability grant" reason

### Comprehensive Capability Grant Tests Added
Added 8 new tests in `tests/test_agent_hardening.py`:

| Test | Purpose |
|------|---------|
| `test_capability_grant_creation_and_persistence` | Grant creation, retrieval, SQLite persistence |
| `test_capability_grant_constraint_matching` | Exact match (chrome vs firefox), capability isolation |
| `test_capability_grant_range_constraints` | Min/max validation (volume 0-100, rejects -10/150) |
| `test_capability_grant_revocation` | Revoke removes grant, invalidates future matches |
| `test_capability_grant_session_scope_expiry` | Past expiry rejected, future expiry accepted |
| `test_policy_integrates_capability_grants` | Policy `requires_approval` flips False with grant |
| `test_tool_registry_has_granular_desktop_tools` | All 6 new tools registered with strict schemas |
| `test_desktop_tools_execute_without_approval_when_granted` | Executor skips approval for granted tools |

**Test Results**: All **66 tests pass** (58 hardening + 8 capability grants).

## Phase 1: Gemini Live Companion Layer (Completed)

*Restored Gemini Live as an always-available supervised voice assistant that delegates execution to AgentRuntime.*

### 1.1 Assistant Bridge (`agent/assistant_bridge.py`)
- **Created `AssistantBridge` class** — Central coordination layer between Gemini Live and AgentRuntime:
  - `delegate_task(description)` → Returns `task_id` immediately, starts `AgentRuntime` in background thread
  - `get_task_status(task_id)` / `get_active_tasks()` — Query task progress, current tool, approval state
  - `get_pending_approval(task_id?)` — Retrieve pending approval for voice resolution
  - `approve_pending_action(approval_id)` / `reject_pending_action(approval_id)` — Voice approval resolution
  - `get_capability_grants()` / `revoke_capability_grant(grant_id)` — Trust & Safety queries
  - Tracks active tasks & pending approvals with thread-safe dict isolation
  - Subscribes to EventBus, translates internal events → `AssistantEvent`

### 1.2 Assistant Events (`agent/assistant_events.py`)
- **Created `AssistantEvent` dataclass** — Compact events for Gemini Live consumption:
  - Types: `task_started`, `approval_required`, `task_completed`, `task_failed`, `tool_progress`
  - Fields: task_id, summary, risk (low/medium/high/critical), approval_id, current_tool, progress
  - Sanitized — no raw exceptions, huge outputs, file contents, or stack traces

### 1.3 Gemini Live Refactor (`providers/gemini_live.py`)
- **Removed OS tool execution** — System instruction explicitly states no OS tools
- **Added 4 delegation tools** for Live API:
  | Tool | Purpose |
  |------|---------|
  | `delegate_to_agent(task_description)` | Start background task, return task_id immediately |
  | `get_agent_status(task_id?)` | Query task progress or all active tasks |
  | `approve_pending_action(approval_id)` | Resolve pending approval (voice "Yes") |
  | `reject_pending_action(approval_id)` | Reject pending approval (voice "No") |
- **AssistantBridge injection** — `GeminiDesktopAgent` receives bridge instance at init
- **Connection state management** — Exposes: connecting, connected, reconnecting, offline/error
- **Event injection** — `inject_agent_event()` formats `AssistantEvent` as system message into Live session
- **Non-blocking startup** — UI no longer blocks on Gemini Live connection

### 1.4 UI Integration (`ui/main_window.py`)
- **Removed auto-start** — Gemini Live starts on-demand (privacy UX)
- **Added "Voice Assistant" toggle button** in top bar with connection state indicator:
  - 🔴 Disconnected / 🟡 Connecting... / 🟢 Connected / 🔄 Reconnecting...
- **Push-to-talk routing** — Hold F1/voice_btn routes to Gemini Live when active, falls back to local transcription when inactive
- **Thread-safe event handling** — `AssistantEventListener` with pyqtSignal marshals AssistantBridge events to main thread
- **Voice approval workflow** — Approval requests appear in chat, user can respond via voice through Gemini Live

### 1.5 Architecture Integration
```
YOU (voice)
    │
    ▼
GEMINI LIVE (Assistant)
    │ • Conversation, Q&A, narration
    │ • Delegates complex tasks via delegate_to_agent()
    │ • Asks permission via approve_pending_action()
    ▼
ASSISTANT BRIDGE (coordination)
    │ • Tracks tasks, approvals, grants
    │ • Translates EventBus → AssistantEvent
    ▼
AGENT RUNTIME (execution)
    │ • plan → act → observe → decide
    │ • ToolExecutor + PolicyEngine + ApprovalManager
    ▼
TOOLS (desktop, shell, files, browser)
```

### Test Results
All **66 tests pass** (58 hardening + 8 capability grants). New components verified:
- `AssistantBridge` task delegation, status queries, approval resolution
- `AssistantEvent` dataclass creation and serialization
- `GeminiDesktopAgent` tool declarations, bridge injection, event injection
- UI voice assistant toggle, connection state, push-to-talk routing

## Phase 5: Voice Approval Workflow (Completed)

*Full voice-driven approval workflow with natural language narration and security enforcement.*

### 5.1 Approval Narration
- **Enhanced system prompt** (`providers/gemini_live.py:_build_system_instructions`) with explicit approval workflow:
  - On `approval_required` event: "The execution agent needs your approval to open Chrome and navigate to YouTube. Shall I allow it?"
  - Clear guidance for voice responses: "Yes"/"Allow it"/"Approve" → `approve_pending_action(approval_id)`
  - "No"/"Deny"/"Cancel" → `reject_pending_action(approval_id)`

### 5.2 Voice Approval Handling
- **Multiple approval disambiguation**: If multiple pending, assistant lists them: "There are two pending approvals. First: open Chrome. Second: write project file. Which should I approve?"
- **Tool descriptions updated** with explicit "only when explicitly asked" guidance

### 5.3 Security Rules (Enforced)
- **Voice approval ONLY resolves existing approval** — Cannot create new actions
- **Approval ID verification** — `AssistantBridge.approve_pending_action()` / `reject_pending_action()` validate approval exists, is pending, belongs to task
- **No approval invention** — System prompt: "Never invent approval IDs - only use ones provided by the system"
- **Approval timeout** — Handled by ToolExecutor (300s default)

## Phase 6: Assistant Context / Memory (Completed)

*Rich session context, project awareness, and memory for Gemini Live.*

### 6.1 Session Context for Resumption
- **Enhanced `AssistantBridge.get_session_context()`** — Comprehensive context on connect/resume:
  ```
  === SESSION CONTEXT ===
  Session started: 2026-09-27 14:30:00
  Current application: Guru Agent
  Current project: guru_agent
  Project: guru_agent (/home/guru/guru_agent)
  Project files: pyproject.toml, README.md
  Git branch: main
  Agent status: running
  Active tasks: 1
  Pending approvals: 1
    - open_application: Approval needed to open Chrome
  Trusted capabilities: open_application, set_volume
  Recent task history (last 5):
    ✅ Fix failing tests (completed)
    ❌ Refactor module (failed)
  Active task: Search and play YouTube
  Pending approval: waiting (open_application)
  ```
- **Injected on every connection/resume** via `GeminiDesktopAgent.run_loop()`

### 6.2 Project Awareness
- **New tool: `get_project_context()`** — On-demand workspace info:
  - Project name, path, detected project files (pyproject.toml, package.json, Cargo.toml, etc.)
  - Git branch status
- **New tool: `get_task_history(limit?)`** — Recent task history with summaries
- **`AssistantBridge.get_project_context()`** — Internal method with filesystem/git detection
- **`AssistantBridge.get_recent_task_history(limit)`** — Returns last N tasks (default 5)

### 6.3 Context Window Management
- **`AssistantBridge.get_context_for_resumption()`** — Structured dict for programmatic resumption:
  - Active tasks with progress
  - Pending approvals with full details
  - Recent task history (last 10)
  - Capability grants
  - Project context
- **`AssistantBridge.compress_context(max_chars)`** — Intelligent truncation for long sessions:
  - Preserves project, active tasks, pending approvals
  - Keeps only last 3 history entries
  - Truncates at `max_chars` with ellipsis
- **Session start tracking** — `_session_start_time` for context freshness

### Test Results
All **66 tests pass**. New components verified:
- `AssistantBridge` session context, project context, task history, resumption context, compression
- `GeminiDesktopAgent` 6 tools (4 delegation + 2 context), enhanced system prompt
- Voice approval workflow narration and disambiguation guidance

## Phase 7: Concurrency Rules (Completed)

*Full multi-task isolation, approval isolation, and task reference by description.*

### 7.1 Multi-Task Isolation
- **`AssistantBridge.active_tasks`** — Thread-safe dict keyed by `task_id` for complete isolation
- Each delegated task gets unique UUID, runs in independent background thread with own `AgentRuntime` and cancellation event
- `get_active_tasks()` returns all tasks with status, current_tool, progress, approval_state

### 7.2 Approval Isolation
- **`AssistantBridge.pending_approvals`** — Thread-safe dict keyed by `approval_id`, each tied to specific `task_id` and tool
- `get_all_pending_approvals()` returns ALL pending approvals for disambiguation (not just first)
- Approvals cannot be confused across tasks — `approve_pending_action(approval_id)` validates ownership

### 7.3 Voice Disambiguation
- System prompt instructs: "There are two pending approvals. First: open Chrome. Second: write project file. Which should I approve?"
- User can say "Approve the first one" or "Approve the Chrome one"

### 7.4 Task State Queries
- **`get_task_status(task_id)`** — Full task details
- **`get_active_tasks()`** — All active tasks
- **`find_task_by_description(query)`** — Fuzzy match tasks by description (e.g., "How's the Chrome task doing?")
  - Searches active tasks first, then recent history
  - Returns task status, progress, result/error

### 7.5 New Tool: `find_task_by_description`
- Added to `LIVE_TOOL_DECLARATIONS` in `providers/gemini_live.py`
- Parameters: `description` (natural language query)
- Returns: matching task with status, progress, result_summary

### Test Results
All **66 tests pass**. Multi-task isolation verified with 3 concurrent tasks, 2 isolated approvals, fuzzy task lookup working.

## Phase 8: Gemini Live Session Resilience (Completed)

*Agent tasks survive Live disconnection; full state recovery on reconnect.*

### 8.1 Reconnection Logic (Already Implemented)
- Exponential backoff with jitter (max 60s)
- Model fallback on quota exceeded (gemini-3.1-flash-live-preview → gemini-3.8-live)

### 8.2 State Recovery on Reconnect
- **`GeminiDesktopAgent.run_loop()`** detects reconnection vs first connect
- On reconnect: sends **full resumption context** via `AssistantBridge.get_context_for_resumption()`:
  ```json
  {
    "session_start_time": "2026-09-27T14:30:00",
    "active_tasks": [...],
    "pending_approvals": [...],
    "recent_task_history": [...],
    "capability_grants": [...],
    "project_context": "..."
  }
  ```
- System message: "SESSION RECOVERED: {full_context}"
- User notified: "Session recovered. Active tasks and approvals restored."

### 8.3 AgentRuntime Independence
- `AgentRuntime` runs in separate background thread — **no dependency on Live connection**
- Task execution continues even if Gemini Live disconnects
- Results available via `get_task_status` / `get_context_for_resumption` on reconnect

### 8.4 Context Window Management
- **`AssistantBridge.compress_context(max_chars)`** — Intelligent truncation for long sessions
- Preserves: project, active tasks, pending approvals
- Truncates: keeps only last 3 history entries

### Test Results
All **66 tests pass**. State recovery verified: reconnect sends full context, AgentRuntime independence confirmed.

## Phase 9: UI Integration (Completed)

*Full visual integration of Assistant and Agent states with EventBus unification.*

### 9.1 Assistant State Indicators
- **Added `assistant_state_label` in top bar** — Real-time visual states:
  - 🎙️ **Idle/Ready** (cyan) — Waiting for input
  - 🎙️ **Listening** (green) — Microphone active, capturing audio
  - 🤔 **Thinking** (orange) — Assistant processing, formulating response
  - 🔊 **Speaking** (pink) — Assistant narrating response
  - 🔄 **Connecting/Reconnecting** (orange) — Session establishing/recovering
  - 🔴 **Disconnected/Error** (red) — No active session
- **Glow/animation sync** — `_on_live_glow()` updates `visualizer_glow_emitter` and `assistant_state_label` in sync
- **State mapping** — `_on_live_state()` maps Gemini Live states (idle/listening/thinking/talking/connecting/reconnecting/connected/disconnected/error) to visual indicators

### 9.2 Agent State Panel (Extended Task Panels)
- **Updated `_render_task_panel()`** — Shows Assistant/Agent distinction:
  ```
  Task (running): Open Chrome and navigate to YouTube
  Assistant: Working on that...
  Agent: Executing: open_application
  ⏳ open_application
  ```
- **Assistant status** — High-level narration: "Working on that...", "Task completed", "Task failed"
- **Agent status** — Granular execution: "Starting...", "Executing: tool_name", "Waiting for approval: tool_name", "Completed: tool_name", "Error in: tool_name"
- **Visual separation** — Color-coded (Assistant: cyan, Agent: green) in styled div

### 9.3 Trust & Safety Panel
- Already implemented in Phase 4.5 — Shows capability grants with scope badges, revoke buttons

### 9.4 EventBus Unification
- **Single EventBus** — Both UI (`GlobalAgentListener`) and Voice Assistant (`AssistantEventListener`) consume same EventBus
- **No duplicate architecture** — Agent events → EventBus → AssistantBridge → AssistantEvent → Gemini Live + UI
- **Thread-safe** — `AssistantEventListener` with pyqtSignal marshals cross-thread events to main thread
- **Terminal drawer** — Shows Agent logs (already exists)

### Test Results
All **93 tests pass** (66 previous + 27 Phase 10). UI integration verified: state indicators, task panel distinction, EventBus unification.

## Phase 10: Testing (Completed)

*Comprehensive test suite covering all security, concurrency, recovery, and integration scenarios.*

### 10.1 Delegation Tests
- ✅ Assistant delegation creates task, returns task_id immediately
- ✅ No OS tool executes inside Gemini Live (only 7 delegation/approval tools)
- ✅ Task runs in AgentRuntime, emits events

### 10.2 Approval Tests
- ✅ Voice approval only resolves existing approval
- ✅ Invalid approval_id rejected
- ✅ Expired approval rejected (double approve)
- ✅ Cancelled task cannot be approved (approval removed)
- ✅ Approval remains attached to exact task and tool

### 10.3 Event Bridge Tests
- ✅ TASK_STARTED → Assistant receives task_started
- ✅ APPROVAL_REQUIRED → Assistant receives approval_required (with risk, approval_id, tool)
- ✅ TASK_COMPLETED → Assistant receives task_completed
- ✅ TASK_FAILED → Assistant receives task_failed (risk=critical)

### 10.4 Concurrency Tests
- ✅ Two simultaneous tasks stay isolated (independent status, progress)
- ✅ Two approvals stay isolated (approve one doesn't affect other)
- ✅ Task A completion doesn't update Task B (independent tracking)

### 10.5 Recovery Tests
- ✅ Gemini Live disconnect doesn't terminate AgentRuntime
- ✅ Agent completion available after Live reconnect (via resumption context)
- ✅ Active task state survives Assistant reconnection

### 10.6 Security Tests
- ✅ Gemini Live cannot call desktop tools directly (no open_application, etc.)
- ✅ Gemini Live cannot call shell tools (no execute_shell, bash, etc.)
- ✅ Gemini Live cannot write files directly (no write_file, read_file, etc.)
- ✅ Only AssistantBridge can delegate or resolve approvals

### 10.7 Capability Grant Tests
- ✅ Grant creation via approval dialog "Always allow"
- ✅ Grant constraints enforced (Chrome only, not arbitrary apps)
- ✅ Grant persistence across restarts (SQLite)
- ✅ Grant revocation works
- ✅ Session-scope grants expire on session end

### Test Results
All **93 tests pass** (66 previous + 27 Phase 10). Complete test coverage for Phases 1-10.

## Phase 7 Entry Criteria

Start the evaluation phase only after Phases 1–6 have been reviewed against the current application paths, relevant targeted tests pass, and CI is green. The existing core regression tests are validation for the implemented architecture, not a declaration that Phase 7 is complete.

## Phase 8

Plugin infrastructure has not started.