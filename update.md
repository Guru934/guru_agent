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

## Phase 7 Entry Criteria

Start the evaluation phase only after Phases 1–6 have been reviewed against the current application paths, relevant targeted tests pass, and CI is green. The existing core regression tests are validation for the implemented architecture, not a declaration that Phase 7 is complete.

## Phase 8

Plugin infrastructure has not started.
