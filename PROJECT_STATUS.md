
# Guru Agent — Project Status

## Current Milestone

**M0 — Stabilize**

Status: ✅ COMPLETE

## Current Objective

Establish a clean, verified baseline before implementing the autonomous coding-agent loop.

## M0 Checklist

- [x] Run the real local test suite (`.venv` is the launcher interpreter but lacks pytest; CI installs pytest)
- [x] Record the actual test result
- [x] Fix or explicitly document every failure
- [x] Stop forwarding ordinary tool-progress events into Gemini Live
- [x] Forward only meaningful task milestones:
  - `STARTED`
  - `APPROVAL_REQUIRED`
  - `BLOCKED`
  - `DONE` / failure
- [x] Protect Guru Agent's own source directory
- [x] Protect `history.db`
- [x] Protect `security_audit.log`
- [x] Remove/fix dead `HEAVY_AGENT_DONE` behavior
- [x] Clean contradictory/stale project documentation
- [x] Review final diff
- [x] Run tests again
- [x] Commit M0

## Verification Record

- Before implementation, `python -m pytest -q` stalled during discovery because
  pytest also searched vendored tests under `archive_legacy`; `pytest.ini` now
  limits default discovery to this repository's `tests/` directory.
- `python -m pytest -q` reaches the suite but aborts in the headless environment
  when Qt tries to use the configured Wayland/X11 display.
- `QT_QPA_PLATFORM=offscreen python -m pytest -q`: **106 passed, 1 skipped**.
- Protected-path policy resolves targets and rejects the Guru Agent source tree,
  `history.db`, and `security_audit.log`. It also denies writes through any
  existing hard-linked file (`st_nlink > 1`), which protects source files
  reached through alternate workspace paths without scanning the source tree.
  This is conservative: unrelated hard-linked files are also not writable;
  ordinary non-hard-linked workspace files remain subject to existing policy.
- The first offscreen run exposed a test using a path now correctly protected
  and a test referencing the pre-existing deleted `README.md`; both fixtures
  were updated to use an allowed temporary workspace and an existing file.
- The only warning is a deprecation warning from the installed `google-genai`
  package. The skipped cancellation test states that its task completed too
  quickly to test cancellation.
- `launch_agent.sh` selects `.venv/bin/python`, where pytest is not installed;
  tests were therefore run with system Python and the same offscreen Qt
  setting used in CI. No packages were installed.

## M0 Definition of Done

M0 is complete only when:

1. The test baseline is known and all remaining failures are understood.
2. Ordinary tool activity does not spam Gemini Live.
3. Guru Agent's own source/state/audit files are protected.
4. Documentation reflects the current architecture.
5. Relevant tests pass after the changes.
6. The changes are committed.

## Current Architecture

```text
USER
  ↓
Gemini Live Assistant
  ↓
AssistantBridge
  ↓
AgentRuntime
  ↓
ToolExecutor
  ↓
PolicyEngine
  ↓
Approval / Capability
  ↓
Registered tools
```

The coding-agent loop and verifier shown in `ROADMAP.md` are planned work, not
current implementation.

## Next Milestone

**M1 — Repo Awareness**

Status: NOT STARTED
