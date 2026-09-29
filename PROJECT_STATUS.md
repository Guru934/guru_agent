
# Guru Agent — Project Status

## Current Milestone

**M4 — Verifier**

Status: ✅ COMPLETE

## Current Objective

Implement deterministic verification beyond the pytest proof used by M3.

## M0 — Stabilize: COMPLETE

### Checklist

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

## M1 Verification Record

- `set_active_project` accepts an existing Git repository, canonicalizes its
  root, rejects Guru Agent's source tree, and persists it in SQLite's existing
  `preferences` table. `get_active_project` revalidates the persisted path.
- `./guru project use <path>` selects a repository and `./guru project show`
  reports exactly the selected canonical repository. Gemini Live also exposes
  project selection and retrieval tools.
- Acceptance tests verified that explicit `repo_path` takes precedence over a
  different active project and that omitted `repo_path` uses the persisted
  active project. Recognized
  repository work without a valid selection fails before launch. Every delegated
  run without a project also has a PolicyEngine guard denying file, search, and
  shell tools, so unrecognized coding phrasing cannot fall back to `APP_DIR`;
  desktop tools remain available.
- A coding delegation with neither explicit nor valid active project was
  rejected before runtime start; no fallback to `/home/guru/guru_agent` occurred.
- Project-bound execution passes the selected root through AgentRuntime,
  ToolExecutor, and PolicyEngine. Reads/writes, shell working directory, and
  search are scoped to the selected project; paths outside it remain denied.
- `QT_QPA_PLATFORM=offscreen python -m pytest -q`: **119 passed, 1 skipped**
  (9 subtests passed). The only warning is the installed `google-genai`
  deprecation warning.

## M1 — Repo Awareness: COMPLETE

## M2 — Coding Tools: COMPLETE

- Added `ToolResult` and active-project tools for file listing, ranged reads,
  ripgrep search, exact-match replacement, Git status/diff, and argv-based
  commands. Tools remain behind ToolExecutor and PolicyEngine.
- Focused M2 verification: **23 passed, 1 skipped** (7 subtests passed).
- Full verification: `QT_QPA_PLATFORM=offscreen python -m pytest -q` —
  **142 passed, 2 skipped** (16 subtests passed). The only warning is the
  installed `google-genai` deprecation warning.
- The protected-source hard-link listing test was skipped because this
  environment's filesystem did not permit creating the test hard link. The
  test reports this reason explicitly. M0 protected-path hard-link behavior
  remains covered by the existing security checks.

## M3 — Vertical Slice: COMPLETE

- A deterministic one-step plan changes `math.py` through `replace_in_file`,
  then runs `tests/test_math.py` through `run_command` in the selected
  repository. Success is reported only when pytest passes; a failing test
  produces a failure result.
- M3 is deliberately limited scaffolding for the canonical add-function
  example. It is not the full coding loop and does not include retries.
- Pytest must be available in the execution environment for verification.
- `QT_QPA_PLATFORM=offscreen python -m pytest -q`: **145 passed, 2 skipped**
  (16 subtests passed). The only warning is the installed `google-genai`
  deprecation warning.

## M4 — Verifier: COMPLETE

- Added deterministic Python, Node, and Rust command detection and structured
  command/attempt/verdict results. Verification executes through ToolExecutor
  and PolicyEngine in the selected or explicitly provided repository.
- Failed command sets are retried exactly once. Both attempts, exit status,
  output truncation, timeout, and error details are retained in the Verdict.
- Focused M4 verification: **17 passed, 1 skipped** (5 subtests passed). The
  Rust execution test skipped because cargo and cargo-clippy are unavailable;
  Rust command detection is covered with tool-availability fixtures.
- Latest full verification: `QT_QPA_PLATFORM=offscreen python -m pytest -q` —
  **162 passed, 3 skipped** (21 subtests passed). The only warning is the
  installed `google-genai` deprecation warning.

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

The full coding-agent loop shown in `ROADMAP.md` remains planned work. The
deterministic repository verifier is implemented; coding actions are not
automatically reflected or retried by it.

## M5 — CodingAgentLoop: IN PROGRESS

### Chunk 1 — Task data model: COMPLETE

- `agent/coding_task.py` — `Status`, `PlanStep`, `Budget`, `CodingTask`
- `tests/test_m5_coding_task.py`
- `Budget.is_exhausted() -> tuple[bool, str]` checks
  action → wall time → tokens, in that order
- Wall-time uses `time.monotonic()`
- Counters record overflow without raising; exhaustion is reported,
  not thrown
- `CodingTask.verification_results` typed against M4's `Verdict`
- No persistence, no loop, no verifier changes, no scope creep
- Commits: `beabd84`, `59e045d`
- Verified: `QT_QPA_PLATFORM=offscreen python -m pytest -q tests/`
  → 191 passed, 2 skipped, 21 subtests passed
- Audited: no test deletions outside the reworked pair
  (`test_cannot_exceed_max_total_action_steps`,
  `test_cannot_exceed_configured_token_budget`)

### Chunk 2 — Role interfaces + adversarial fakes: NEXT
