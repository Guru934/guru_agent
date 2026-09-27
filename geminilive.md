# Implementation Plan: Gemini Live + Agent Integration v2

## Overview
This plan restores the always-available Gemini Live voice assistant as a **supervised companion layer** that delegates execution to the secure AgentRuntime, while introducing a **Trusted Capability System** for fast-path trusted actions. The architecture enforces a single security boundary (ToolExecutor + PolicyEngine + ApprovalManager) with two execution paths: fast trusted capabilities and heavy AgentRuntime reasoning.

---

## Requirements Restatement

### Core Architecture Goals
1. **Gemini Live as Assistant/Supervisor** — Handles conversation, intent understanding, simple Q&A, narrates progress, asks permission, reports results
2. **AgentRuntime as Execution Engine** — Handles complex multi-step tasks: plan → act → observe → decide
3. **Single Security Boundary** — ToolExecutor + PolicyEngine + ApprovalManager + Capability Grants
4. **Two Execution Speeds** — 
   - Fast: Trusted Capabilities (open Chrome, set volume, play/pause)
   - Heavy: AgentRuntime (search project, fix tests, write code)
4. **Reverse Event Channel** — Agent events → AssistantEventBridge → Gemini Live for real-time narration
5. **Voice Approval Workflow** — User approves pending actions via voice, resolving exact approval IDs
6. **Session Resilience** — Agent tasks survive Gemini Live disconnection/reconnection

### Current State (from codebase analysis)
- **Phases 1-6 implemented** but need hardening (see update.md, PROJECT_STATUS.md)
- **AgentRuntime** exists with plan/act/observe loop
- **ToolExecutor** with PolicyEngine and ApprovalManager as central choke point
- **EventBus** emits TASK_STARTED, TOOL_REQUESTED, APPROVAL_REQUIRED, TOOL_FINISHED, TASK_COMPLETED, TASK_FAILED
- **Gemini Live provider** exists but disabled (no tools, separate from main pipeline)
- **UI** (ScratchpadWindow) listens to EventBus, shows task panels, handles approvals via dialog
- **Tools registered**: execute_shell, write_file, read_file, search, desktop_action, describe_current_screen, describe_active_window
- **desktop_action** is monolithic high-risk tool parsing free-text requests

---

## Implementation Phases

### Phase 0: Prerequisites & Hardening (Complete Phase 1-6 Entry Criteria)
*Must satisfy Phase 7 entry criteria from update.md before proceeding*

- [ ] 0.1 Run full test suite and ensure CI passes
- [ ] 0.2 Verify schema validation, shell policy, approval timeout/cancellation, worker-thread execution, runtime lifecycle tests pass
- [ ] 0.3 Audit all tool execution paths flow through ToolExecutor (no bypasses)
- [ ] 0.4 Confirm workspace confinement works for file tools
- [ ] 0.5 Document any remaining gaps in Phase 1-6

---

### Phase 4.5: Trusted Capability / Permission System (NEW PRIORITY)
*Build this BEFORE Gemini Live integration — it's the foundation for fast-path actions*

#### 4.5.1 Capability Registry & Grants Storage
- [ ] **Create `agent/capabilities.py`** — Capability definitions and grant management
  - `CapabilityGrant` dataclass: capability_name, constraints (JSON), scope (session/persistent), enabled, created_at, expires_at
  - `CapabilityRegistry` class: register capabilities, check grants, evaluate constraints
  - Constraints are parameter-scoped (e.g., `open_application` constrained to `app_name="chrome"`)

- [ ] **Create `agent/permissions.py`** — Permission decision logic
  - `PermissionDecision` extends PolicyDecision with `source` (user_grant, policy_default, blocked)
  - Integrates with PolicyEngine: capability grants change `requires_approval=True` → `False` for matching capabilities
  - Grants never bypass ToolExecutor — only change approval requirement

- [ ] **Add persistence** — SQLite table `capability_grants` in `memory/sqlite.py`
  - Columns: id, capability, constraints_json, scope, enabled, created_at, expires_at
  - Survives application restarts

#### 4.5.2 Capability Definitions (Replace monolithic desktop_action)
- [ ] **Split `desktop_action` into granular capabilities** in `agent/tool_registry.py`:
  - `open_application` — constraints: allowed app names list
  - `open_url` — constraints: allowed domains/URLs list  
  - `set_volume` — constraints: min/max range (0-100)
  - `set_brightness` — constraints: min/max range (0-100)
  - `media_control` — constraints: allowed actions (play, pause, next, previous)
  - `get_clipboard` — no constraints needed (low risk)
  - `search_and_play_youtube` — constraints: allowed query patterns?

- [ ] **Update `tools/desktop.py`** — Add individual handler functions for each capability
  - Each handler takes typed parameters (not free-text)
  - Maintain `handle_desktop_action` as legacy fallback for compatibility

#### 4.5.3 Permission UI & Management
- [ ] **Add "Trust & Safety" panel in UI** (Settings or sidebar)
  - Show: Always Allowed, Ask When Needed, Blocked
  - Each grant: [Session Only] [Always] [Revoke] buttons
  - Voice command: "What are you allowed to do?" → Assistant reads grants

- [ ] **Approval dialog enhancement** — Add "Always allow this specific action" checkbox
  - When checked, creates persistent CapabilityGrant with exact constraints
  - Example: Approving `open_application("chrome")` → grant for Chrome only

#### 4.5.4 Integration with PolicyEngine
- [ ] **Modify `agent/policy.py`** — Check capability grants before returning `requires_approval`
  - New method: `check_capability_grant(tool_name, arguments) -> bool`
  - If grant exists and matches constraints exactly → `requires_approval=False`
  - Grants are additive — don't weaken other policy rules (workspace, blocked commands)

---

### Phase 1: Restore Gemini Live as Companion Layer

#### 1.1 Refactor `providers/gemini_live.py`
- [ ] **Remove OS tool execution** — Already done (system_instruction says "no OS tools")
- [ ] **Add delegation function** — `delegate_to_agent(task_description)` returns task_id immediately
- [ ] **Add status query function** — `get_agent_status(task_id)`
- [ ] **Add approval functions** — `approve_pending_action(approval_id)`, `reject_pending_action(approval_id)`
- [ ] **Add AssistantBridge reference** — Inject `AssistantBridge` instance for delegation/status
- [ ] **Connection state management** — Expose: connecting, connected, reconnecting, offline/error
- [ ] **Non-blocking startup** — UI must not block on Gemini Live connection

#### 1.2 Update `GeminiDesktopAgent` class
- [ ] **Add `assistant_bridge` parameter** to `__init__`
- [ ] **Register Live tools** in `LiveConnectConfig`:
  ```python
  tools = [
      types.FunctionDeclaration(name="delegate_to_agent", ...),
      types.FunctionDeclaration(name="get_agent_status", ...),
      types.FunctionDeclaration(name="approve_pending_action", ...),
      types.FunctionDeclaration(name="reject_pending_action", ...),
  ]
  ```
- [ ] **Handle tool calls** in `receive_worker()` — route to AssistantBridge
- [ ] **Immediate return** — `delegate_to_agent` returns task_id, doesn't wait for completion
- [ ] **Inject system context** — Periodic updates on active tasks, pending approvals

#### 1.3 Update UI Integration (`ui/main_window.py`)
- [ ] **Remove auto-start** — Gemini Live starts on-demand (privacy UX)
- [ ] **Add "Start Voice Assistant" button/toggle** in top bar
- [ ] **Show connection state** — Visual indicator: 🔴 Disconnected, 🟡 Connecting, 🟢 Connected
- [ ] **Route voice input** — Push-to-talk (F1/voice_btn) sends to Gemini Live, not local transcription

---

### Phase 2: Create Assistant Control Plane (`agent/assistant_bridge.py`)

#### 2.1 Core Bridge Class
- [ ] **Create `agent/assistant_bridge.py`** with `AssistantBridge` class:
  ```python
  class AssistantBridge:
      def delegate_task(self, description: str) -> str:           # Returns task_id
      def get_task_status(self, task_id: str) -> dict:
      def get_active_tasks(self) -> list[dict]:
      def get_pending_approval(self, task_id: str | None = None) -> dict | None:
      def approve_pending_action(self, approval_id: str) -> str:
      def reject_pending_action(self, approval_id: str) -> str:
      def get_capability_grants(self) -> list[dict]:              # For "what can you do?"
      def revoke_capability_grant(self, grant_id: str) -> bool:
  ```

#### 2.2 Task Management
- [ ] **Track active tasks** — `active_tasks: dict[str, TaskSummary]`
- [ ] **Track pending approvals** — `pending_approvals: dict[str, ApprovalSummary]`
- [ ] **Concurrency support** — Multiple tasks isolated by task_id
- [ ] **Task lifecycle** — Start via `AgentRuntime.run()` in background thread

#### 2.3 Security Enforcement
- [ ] **Bridge never executes OS tools directly** — Only coordinates
- [ ] **Approval resolution** — Verifies: approval exists, pending, belongs to task, not expired, not cancelled
- [ ] **Voice approval safety** — Cannot invent approval IDs, only resolve existing ones

---

### Phase 3: Add Gemini Live Delegation Tools

#### 3.1 Tool Declarations
- [ ] **`delegate_to_agent(task_description: str)`** 
  - Creates task_id, starts AgentRuntime, returns task_id immediately
  - System prompt addition: "You can delegate complex tasks to the execution agent..."

- [ ] **`get_agent_status(task_id: str | None = None)`**
  - Returns: status, current_tool, current_step, progress_summary, approval_state, result_summary
  - If task_id=None, returns all active tasks summary

- [ ] **`approve_pending_action(approval_id: str)`**
  - Validates approval exists, pending, not expired
  - Calls `ApprovalManager.approve(approval_id)`
  - Returns result or error message

- [ ] **`reject_pending_action(approval_id: str)`**
  - Same validation, calls `ApprovalManager.reject(approval_id)`

#### 3.2 Tool Schemas (JSON for Live API)
- [ ] Define strict input schemas for each function
- [ ] Add descriptions that guide Gemini on when to use each

---

### Phase 4: Agent → Assistant Event Bridge

#### 4.1 AssistantEvent Data Structures
- [ ] **Create `agent/assistant_events.py`** — Compact events for Assistant consumption:
  ```python
  @dataclass
  class AssistantEvent:
      type: Literal["task_started", "approval_required", "task_completed", "task_failed", "tool_progress"]
      task_id: str
      summary: str                      # Human-readable
      risk: Literal["low", "medium", "high", "critical"] | None = None
      approval_id: str | None = None
      current_tool: str | None = None
      progress: str | None = None
  ```

#### 4.2 Event Translation in AssistantBridge
- [ ] **Subscribe to EventBus** in `AssistantBridge.__init__`
- [ ] **Translate internal events → AssistantEvent**:
  - `TASK_STARTED` → `task_started` with summary
  - `APPROVAL_REQUIRED` → `approval_required` with summary, risk, approval_id
  - `TOOL_STARTED`/`TOOL_FINISHED` → `tool_progress` with current_tool, progress
  - `TASK_COMPLETED` → `task_completed` with result summary
  - `TASK_FAILED` → `task_failed` with error summary
- [ ] **Filter/sanitize** — No raw exceptions, huge outputs, file contents, stack traces

#### 4.3 Push to Gemini Live
- [ ] **Add `notify_agent_event(event: AssistantEvent)` to `GeminiDesktopAgent`**
- [ ] **Thread-safe injection** — Use `loop.call_soon_threadsafe()` from Agent threads
- [ ] **Format as system message** — Inject structured context into Live session:
  ```
  SYSTEM: Execution agent update:
  task_id=abc123
  status=waiting_for_approval
  summary=Open Chrome and navigate to YouTube
  risk=high
  ```

---

### Phase 5: Voice Approval Workflow

#### 5.1 Approval Narration
- [ ] **Gemini Live receives `approval_required` event** → Speaks:
  > "The execution agent needs your approval to open Chrome and navigate to YouTube. Shall I allow it?"

#### 5.2 Voice Approval Handling
- [ ] **User says "Yes" / "Allow it" / "Approve"** → Gemini calls `approve_pending_action(approval_id)`
- [ ] **User says "No" / "Deny" / "Cancel"** → Gemini calls `reject_pending_action(approval_id)`
- [ ] **Multiple pending approvals** — Assistant asks: "There are two pending approvals. The first is to open Chrome; the second is to write the project file. Which one should I approve?"

#### 5.3 Security Rules (Critical)
- [ ] **Voice approval ONLY resolves existing approval** — Cannot create new actions
- [ ] **Verify approval_id matches** pending approval in AssistantBridge
- [ ] **Optional GUI confirmation** for critical actions (configurable)
- [ ] **Approval expires** — Timeout handled by ToolExecutor (already 300s)

---

### Phase 6: Assistant Context / Memory

#### 6.1 Session Context for Gemini Live
- [ ] **Provide compact context on session start/resume**:
  ```
  Current application: Guru Agent
  Current project: guru_agent
  Agent status: running
  Active task: Run tests for Gemini Live integration
  Pending approval: None
  Trusted capabilities: Open Chrome, Open YouTube, Set volume, Media controls
  ```

#### 6.2 Project Awareness
- [ ] **On-demand file/project info** — Assistant delegates to Agent for workspace queries
- [ ] **Recent task history** — Last 5 tasks with summaries

#### 6.3 Context Window Management
- [ ] **Session resumption** — Use Gemini Live session resumption API
- [ ] **Context compression** — Summarize old conversations for long sessions

---

### Phase 7: Concurrency Rules

#### 7.1 Multi-Task Isolation
- [ ] **Each task has unique task_id** — AssistantBridge maintains dict by task_id
- [ ] **Approval isolation** — Approval tied to specific task_id and tool
- [ ] **Voice disambiguation** — If multiple approvals pending, Assistant lists them

#### 7.2 Task State Queries
- [ ] **`get_active_tasks()`** returns all tasks with status
- [ ] **Assistant can reference tasks by description** — "How's the Chrome task doing?"

---

### Phase 8: Gemini Live Session Resilience

#### 8.1 Reconnection Logic
- [ ] **Exponential backoff with jitter** — Already implemented in gemini_live.py
- [ ] **Model fallback** — Already implemented (quota exceeded → fallback model)

#### 8.2 State Recovery
- [ ] **Agent tasks continue independently** — AgentRuntime doesn't depend on Live connection
- [ ] **On reconnect**: AssistantBridge sends current state to Gemini Live
  - Active tasks with progress
  - Pending approvals
  - Recent completions/failures
- [ ] **Context window compression** for long-lived sessions

---

### Phase 9: UI Integration

#### 9.1 Assistant State Indicators
- [ ] **Visual states**: Listening 🎙️, Thinking 🤔, Speaking 🔊, Reconnecting 🔄
- [ ] **Glow/animation sync** — Already have visualizer_state_emitter, visualizer_glow_emitter

#### 9.2 Agent State Panel
- [ ] **Extend existing task panels** with Assistant/Agent distinction:
  ```
  Assistant: "Working on that..."
  Agent: [Reading project files] [Running tests] [Waiting for approval]
  ```

#### 9.3 Trust & Safety Panel
- [ ] **New UI section** showing capability grants (from Phase 4.5.3)
- [ ] **Revoke buttons** for each grant
- [ ] **Session vs Persistent** badges

#### 9.4 EventBus Unification
- [ ] **UI and Voice Assistant consume same EventBus** — No duplicate architecture
- [ ] **Terminal drawer** shows Agent logs (already exists)

---

### Phase 10: Testing

#### 10.1 Delegation Tests
- [ ] Assistant delegation creates task, returns task_id immediately
- [ ] No OS tool executes inside Gemini Live
- [ ] Task runs in AgentRuntime, emits events

#### 10.2 Approval Tests
- [ ] Voice approval only resolves existing approval
- [ ] Invalid approval_id rejected
- [ ] Expired approval rejected
- [ ] Cancelled task cannot be approved
- [ ] Approval remains attached to exact task and tool

#### 10.3 Event Bridge Tests
- [ ] TASK_STARTED → Assistant receives task_started
- [ ] APPROVAL_REQUIRED → Assistant receives approval_required
- [ ] TASK_COMPLETED → Assistant receives task_completed
- [ ] TASK_FAILED → Assistant receives task_failed

#### 10.4 Concurrency Tests
- [ ] Two simultaneous tasks stay isolated
- [ ] Two approvals stay isolated
- [ ] Task A completion doesn't update Task B

#### 10.5 Recovery Tests
- [ ] Gemini Live disconnect doesn't terminate AgentRuntime
- [ ] Agent completion available after Live reconnect
- [ ] Active task state survives Assistant reconnection

#### 10.6 Security Tests
- [ ] Gemini Live cannot call desktop tools directly
- [ ] Gemini Live cannot call shell tools
- [ ] Gemini Live cannot write files directly
- [ ] Only AssistantBridge can delegate or resolve approvals

#### 10.7 Capability Grant Tests
- [ ] Grant creation via approval dialog "Always allow"
- [ ] Grant constraints enforced (Chrome only, not arbitrary apps)
- [ ] Grant persistence across restarts
- [ ] Grant revocation works
- [ ] Session-scope grants expire on session end

---

## Dependencies

### External APIs/Services
- **Google Gemini Live API** — `google-genai>=1.0.0` (already in requirements)
- **Audio I/O** — `PyAudio`, system audio (wpctl, pulseaudio/pipewire)
- **Desktop Automation** — `xdg-open`, `wpctl`, `brightnessctl`, `wl-paste`/`xclip`

### Internal Dependencies
- **AgentRuntime** — Must be stable (Phase 2 complete)
- **ToolExecutor + PolicyEngine + ApprovalManager** — Core security boundary
- **EventBus** — For Agent → Assistant events
- **SQLite memory** — For capability grant persistence
- **UI (PyQt6)** — For visual indicators and Trust & Safety panel

---

## Risks

### HIGH — Critical Risks That Could Block Implementation

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Gemini Live API changes** | Breaks tool calling, session management | Pin `google-genai` version; monitor Google AI docs; abstraction layer for Live API |
| **Voice approval security bypass** | User voice → arbitrary command execution | Strict approval_id validation; capability grants parameter-scoped; GUI confirmation for critical |
| **EventBus thread safety** | Race conditions, lost events | Use `threading.RLock`; `call_soon_threadsafe` for cross-thread; test concurrently |
| **Capability grant constraint matching** | Over-permissive grants (e.g., "chrome" matches "chrome --dangerous") | Exact match or strict prefix matching; validate constraints at grant creation |
| **Session resumption not working** | Assistant loses context on reconnect | Test with actual API; implement fallback context reconstruction from EventBus |

### MEDIUM — Moderate Risks to Address

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Audio latency/quality** | Poor voice experience | Test on target hardware; buffer tuning; earcon feedback |
| **Multiple concurrent approvals** | User confusion | Clear voice disambiguation; visual panel shows all pending |
| **Context window overflow** | Long sessions degrade | Implement summarization; Gemini Live context compression |
| **Tool schema drift** | Live tools vs registry mismatch | Single source of truth: tool_registry.py generates Live schemas |

### LOW — Minor Concerns

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Model fallback during task** | Task uses different model mid-execution | Delegate task uses fixed model; only Live assistant switches |
| **UI glow/state sync** | Visual feedback lag | Already implemented via emitters; verify |
| **Legacy desktop_action fallback** | Confusion if both exist | Deprecate with warning; migrate all calls |

---

## Estimated Complexity

| Phase | Complexity | Estimated Time |
|-------|------------|----------------|
| Phase 0: Prerequisites | MEDIUM | 1-2 days (testing/hardening) |
| Phase 4.5: Capability System | HIGH | 3-5 days (new module, UI, persistence) |
| Phase 1: Gemini Live Companion | MEDIUM | 2-3 days (refactor, tools, UI) |
| Phase 2: Assistant Bridge | MEDIUM | 2-3 days (new module, event integration) |
| Phase 3: Delegation Tools | LOW | 1-2 days (tool declarations) |
| Phase 4: Event Bridge | MEDIUM | 2-3 days (translation, thread-safe push) |
| Phase 5: Voice Approval | MEDIUM | 2-3 days (narration, security) |
| Phase 6: Context/Memory | LOW | 1-2 days (compact context) |
| Phase 7: Concurrency | LOW | 1 day (dict isolation) |
| Phase 8: Resilience | MEDIUM | 2-3 days (recovery, compression) |
| Phase 9: UI Integration | MEDIUM | 2-3 days (panels, indicators) |
| Phase 10: Testing | HIGH | 3-5 days (comprehensive test suite) |

**Total Estimated: 22-37 days** (sequential, single developer)

---

## File Changes Summary

### New Files
| File | Purpose |
|------|---------|
| `agent/capabilities.py` | Capability registry, grants, constraint evaluation |
| `agent/permissions.py` | Permission decision with capability grant integration |
| `agent/assistant_bridge.py` | AssistantBridge — coordination layer |
| `agent/assistant_events.py` | Compact AssistantEvent dataclasses |
| `memory/sqlite.py` additions | `capability_grants` table, CRUD operations |

### Modified Files
| File | Changes |
|------|---------|
| `agent/tool_registry.py` | Split desktop_action → granular capabilities; add schemas |
| `tools/desktop.py` | Individual typed handlers for each capability |
| `agent/policy.py` | Check capability grants before requiring approval |
| `providers/gemini_live.py` | Add delegation tools, AssistantBridge injection, event injection |
| `ui/main_window.py` | Voice assistant toggle, connection state, Trust & Safety panel |
| `agent/executor.py` | (Minor) Ensure approval context includes task_id for bridge |
| `config.py` | (Optional) Capability grant settings |

---

## Success Criteria

- [ ] **Gemini Live runs as always-available voice assistant** (manual start, not auto)
- [ ] **Simple Q&A works without Agent** ("What is Python inheritance?")
- [ ] **Complex tasks delegate to AgentRuntime** ("Fix the failing tests")
- [ ] **Voice approval works** — User says "Yes" → Agent executes
- [ ] **Trusted capabilities execute instantly** — "Open Chrome" → immediate (no approval)
- [ ] **Agent events narrated in real-time** — "The agent is running tests... 38 passed"
- [ ] **Agent survives Live disconnect** — Task completes, result available on reconnect
- [ ] **Security boundary intact** — No OS tool executes without ToolExecutor+Policy+Approval
- [ ] **Capability grants persist** — Survive restart, scoped to exact parameters
- [ ] **All Phase 10 tests pass** — Delegation, approval, events, concurrency, recovery, security

---

## Architecture Diagram (Final Target)

```text
                         YOU
                  voice / keyboard
                         │
                         ▼
              ┌─────────────────────┐
              │   GEMINI LIVE       │
              │   "Assistant"       │
              │                     │
              │ • conversation      │
              │ • understand intent │
              │ • answer simple Qs  │
              │ • narrate progress  │
              │ • ask permission    │
              │ • report results    │
              │ • delegate work     │
              └──────────┬──────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
       FAST TRUSTED            COMPLEX TASK
       CAPABILITY                  │
              │                     ▼
              ▼            ┌──────────────────┐
       Capability        │   AGENT RUNTIME  │
       Broker            │                  │
              │          │ plan → act →     │
              │          │ observe → decide │
              └──────────┼──────────────────┘
                         │
                  ToolExecutor
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
         Capability   Policy      Approval
         Grants       Engine      Manager
              │          │          │
              └──────────┼──────────┘
                         ▼
                   ToolExecutor
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
           Desktop    Browser    Files/Shell
                         │
                         ▼
                      EventBus
                         │
                         ▼
              AssistantEventBridge
                         │
                         ▼
              Gemini Live Session
                         │
                         ▼
                        YOU
```

---

## Next Steps

1. **Complete Phase 0** — Verify Phase 1-6 hardening is complete
2. **Begin Phase 4.5** — Build Trusted Capability System (foundation)
3. **Proceed sequentially** — Each phase builds on previous
4. **Run tests continuously** — Phase 10 tests written alongside implementation

---

**Document Version**: 1.0  
**Created**: Based on architecture discussion and codebase analysis  
**Project**: Guru Agent (`/home/guru/guru_agent`)  
**Target File**: `geminilive.md`
