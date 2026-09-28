Use this:

```markdown
# Guru Agent — Coding Instructions

## Responsibilities
   # Gemini Live Assistant
conversation
intent understanding
delegation
approval dialogue
milestone narration
final summaries

It must not become the coding worker.

  # Coding Agent
understand repository
plan work
modify code
run verification
diagnose failures
retry within limits

# Verifier

The verifier is the source of truth.

A model saying "done" is never sufficient.

## Non-Negotiable Rules
Work on one milestone at a time.
Do not implement future milestones unless explicitly requested.
Inspect existing architecture before editing.
Prefer the smallest compatible change.
Do not bypass ToolExecutor or PolicyEngine.
Do not claim success without verification evidence.
Never let model-generated completion override a failing verifier.
Never silently modify a repository outside the active project.
Never auto-commit during coding-agent execution unless explicitly designed and approved later.
Keep unrelated cleanup out of milestone work.

# Failure Controls

These must be designed into the agent loop from the beginning.

Stale context

After a file is modified, invalidate its cached contents.
The agent must re-read the file before reasoning from it again.

# Impossible tasks

The planner may return:

{
  "steps": [],
  "reason": "cannot be completed because X"
}

The task becomes BLOCKED; the agent must not invent success.

# Flaky tests

Retry verification once before sending the failure into reflection.

# Runaway execution

Hard limits:

max_steps = 20
max_attempts_per_step = 3
max_wall_time = 20 minutes
max_tokens_per_task = configured budget

Any limit hit results in BLOCKED with a summary of what was attempted.

Model lies

The reflector may suggest a fix, but only the verifier can establish success.

# Tool Result Contract

All coding-agent tools should converge on:

@dataclass
class ToolResult:
    ok: bool
    summary: str
    details: str
    changed: bool
    artifact: str | None
    truncated: bool

For command output, prefer head + tail truncation:

first 50 lines
last 50 lines

This preserves useful failure information at the end of logs.

## Source of Truth

This repository uses these project documents:

- `AGENTS.md` — engineering rules that always apply.
- `ROADMAP.md` — canonical implementation roadmap and milestone definitions.
- `PROJECT_STATUS.md` — current implementation status and verified completion.

Read the relevant document before making substantial changes.

`ROADMAP.md` defines what should be built.
`PROJECT_STATUS.md` defines what is actually completed.
`AGENTS.md` defines rules that must always be followed.

Do not treat an AI-generated claim of completion as project status.

## Current execution architecture

Gemini Live is the conversational supervisor.

Delegated work currently runs through `AssistantBridge`, `AgentRuntime`, and the registered tools.
The roadmap's `CodingAgentLoop` is future work and is not implemented yet.

Do not merge these responsibilities.

Core flow:

USER
→ Gemini Live
→ AssistantBridge
→ AgentRuntime
→ ToolExecutor
→ PolicyEngine
→ Approval / Capability
→ Registered tools

The future coding flow is defined in `ROADMAP.md`:

PLAN
→ ACT
→ VERIFY
→ REFLECT
→ RETRY
→ DONE / BLOCKED

## Verification

The verifier is the source of truth.

Never report a task as successful when verification has failed.

Never bypass verification because the model believes its implementation is correct.

## Security

All tools must pass through `ToolExecutor` and `PolicyEngine`.

Never bypass workspace restrictions.

Never bypass approval/capability controls.

Never silently operate on a repository outside the active project.

Protect Guru Agent's own source, database, and audit state.

## Scope Control

Work on one roadmap milestone at a time.

Do not implement future milestones unless explicitly requested.

Do not perform unrelated cleanup or refactoring.

Prefer the smallest compatible change.

## Testing

Run the relevant tests after every implementation change.

Do not claim success without test evidence.

When a test fails:

1. determine the actual cause,
2. fix the cause,
3. rerun the test.

## Git

Review the diff before committing.

Do not overwrite unrelated user changes.

Do not auto-commit unless the current milestone explicitly requires it.

## Token / Context Discipline

Keep work focused.

Do not reread the entire repository unnecessarily.

Prefer targeted file inspection.

Avoid verbose explanations when a concise engineering report is sufficient.

Before editing, identify:
- files that need changing,
- why they need changing,
- what must remain untouched.

## Current Work

M0 — Stabilize, M1 — Repo Awareness, M2 — Coding Tools, M3 — Vertical Slice,
and M4 — Verifier are complete. M5 — CodingAgentLoop is next and is not
started. Do not begin M5 unless explicitly requested.

Follow `PROJECT_STATUS.md` for current milestone state and `ROADMAP.md` for
milestone scope and acceptance criteria.
