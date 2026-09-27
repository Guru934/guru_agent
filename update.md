# Project Update Log

## Current Status

**Phase 1–6 hardening and integration changes are implemented locally.** The project has not yet cleared the final Phase 1–6 completion gate: review the remaining security boundaries and confirm GitHub Actions passes on the published commit. Phase 7 remains deferred until that gate is met. Phase 8 has not started.

## Work Completed

### Phase 1 — Unified Tool Execution

- Agent-requested tool calls pass through argument validation, policy evaluation, approval when required, and the shared executor before registered handlers execute.
- Approval waits have a finite timeout and respond to task cancellation. An approved operation runs on its waiting background worker instead of executing on the UI thread.
- Removed the normal-chat XML tool parser and its separate provider worker.
- Removed direct desktop actions from the chat UI; supported desktop operations are registered agent tools.

### Phase 2 — Agent Runtime and Providers

- Keyboard chat and transcribed voice input share the same `AgentRuntime` request path.
- Gemini and Ollama use provider adapters with a common response and tool-call interface.
- Direct Q&A can run without exposing tools; delegated tasks and screen/desktop requests enable the required tools.
- Cancellation tokens are scoped to task lifetime, and duplicate active task IDs are rejected.

### Phase 3 — Structured Tool Calls

- Tool schemas use provider-independent JSON types.
- Required fields, argument types, nested values, and undeclared properties are validated before policy evaluation.
- Removed the legacy XML `<read>`, `<search>`, `<bash>`, and `<write>` parsing path.

### Phase 4 — Workspace and Shell Policy

- Filesystem tools resolve paths against configured workspace roots, including symlink resolution; direct handler calls enforce the same boundary.
- Shell policy parses commands rather than trusting string prefixes. A narrow read-only allowlist runs without approval; blocked destructive executables are denied.
- Shell execution uses a fixed working directory, a filtered environment, a timeout, process-group termination on timeout, and a bounded output buffer.
- Audit records avoid storing raw command text and file contents; execution is denied if the audit log cannot be written.
- CI now installs `portaudio19-dev`, addressing the observed `PyAudio` build failure caused by missing `portaudio.h`.

### Phase 5 — Voice and Realtime Provider

- Transcribed push-to-talk messages are submitted through the same runtime as keyboard messages.
- Gemini Live no longer registers or executes privileged OS tools directly; desktop actions use the main runtime and its policy/approval flow.

### Phase 6 — Task Observability

- Task panels and tool steps are keyed by task ID, isolating concurrent task progress.
- Approval, tool completion, timeout, and task failure states are reflected in task progress.
- Event subscriptions are synchronized and removed when the UI closes.

## Validation Performed

- Full local test suite after stabilizing the Qt test lifecycle: **38 passed**.
- Python compilation completed successfully.
- `git diff --check` completed successfully.
- GitHub Actions initially failed during dependency installation because `portaudio.h` was missing; the workflow now installs `portaudio19-dev`.
- The first post-publish CI run passed dependency installation but aborted in newly added UI tests when Qt attempted to initialize a second application instance. The unstable extra widget tests were removed; confirm the next GitHub Actions run passes.

## Remaining Work and Limitations

1. Confirm the latest GitHub Actions run passes after the Qt test adjustment. Fix any failures before declaring Phases 1–6 complete.
2. Review the execution paths and security assumptions against the target desktop environment.
3. **This is not an OS sandbox.** Arbitrary shell commands permitted with safe mode disabled, or approved while safe mode is enabled, can access files outside the configured workspace. Do not use unattended arbitrary shell execution as if workspace policy confined it; stronger OS-level isolation remains future work.
4. Once Phase 1–6 review and CI are green, proceed to Phase 7 evaluation work, including broader boundary coverage and explicit cancellation, approval-bypass, and resource-use cases.
5. Phase 8 plugin infrastructure (including Calendar, browser-agent, and RAG integrations) has not started.
