# Guru Agent Roadmap

## Mission

Build Guru Agent into a reliable local-first desktop AI assistant where:

- Gemini Live is the conversational supervisor.
- A coding agent performs repository-level engineering work.
- All meaningful changes are verified deterministically.
- Failed work is diagnosed and retried within strict limits.
- Risky actions remain protected by the existing security boundary.

The core product goal is:

> Reliably turn a request such as "fix X" into a verified repository change with passing tests.

---

# Target Architecture

This is the intended architecture as later milestones are implemented; it does
not describe the current runtime. The current execution flow is recorded in
`PROJECT_STATUS.md`.

text
USER
  ↓
Gemini Live Assistant
  ↓
AssistantBridge
  ↓
CodingAgentLoop
  ↓
PLAN → ACT → VERIFY → REFLECT → RETRY
  ↓
Coding Tools
  ↓
ToolExecutor
  ↓
PolicyEngine
  ↓
Approval / Capability Grant
  ↓
Verifier
  ↓
PASS → DONE
or
FAIL → REFLECT → RETRY
or
BLOCKED


# Roadmap

## M0 — Stabilize

### Work

- Run the full local test suite and record the real baseline.
- Fix or explicitly document every failure.
- Stop forwarding ordinary tool_progress events into Gemini Live.
- Only forward meaningful task milestones:
  - STARTED
  - APPROVAL_REQUIRED
  - BLOCKED
  - DONE / task failure
- Protect Guru Agent's own:
  - source directory
  - history.db
  - security_audit.log
- Clean contradictory/stale documentation.
- Fix or remove dead HEAVY_AGENT_DONE behavior.

### Done when

`pytest -q` is clean or every remaining failure is explicitly understood and documented, and ordinary tool activity no longer causes Gemini Live chatter.

## M1 — Repo Awareness

### Work

- Add set_active_project(path).
- Add get_active_project().
- Persist the active project in SQLite.
- Extend `delegate_task(task, repo_path=None)`.
- Add assistant support for selecting/using a project.
- Never silently default coding tasks to Guru Agent's own source repository.

### Done when

`guru project use ~/test-repo` and `guru project show` show the correct repository and delegated coding tasks use that repository.

## M2 — Coding Tools

Add repo-aware tools through the existing security boundary:

- `list_files(glob, max=200)`
- `read_file(path, start_line=None, end_line=None)`
- `search(query, path=None, glob=None)`
- `replace_in_file(path, old, new)`
- `git_status()`
- `git_diff()`
- `run_command(argv, cwd, timeout)`

### Required safety rules

`replace_in_file`:

- exact match required
- old text must match exactly once
- zero matches → fail
- multiple matches → fail

`run_command`:

- accepts argv list
- no shell=True
- explicit working directory
- timeout
- process-group termination
- bounded output

All tools must pass through:

`ToolExecutor` → `PolicyEngine` → `Approval / Capability`

### Done when

Every tool works correctly against a toy repository and has tests covering success and important failure cases.

## M3 — Vertical Slice

Build the smallest end-to-end loop proving:

`Planner` → `Actor` → `Verifier` → `Reflector`

A hardcoded/simple planner and reflector are acceptable.

Example:

```text
$ guru code "add a function add(a, b) to math.py and a test"

[plan] 1 step
[act] replace_in_file math.py
[verify] pytest tests/test_math.py → exit 0
[done] 1 file changed, 1 test passed
```

### Done when

The complete interface works end-to-end on a throwaway repository.

## M4 — Verifier

Add deterministic verification.

### Command detection

- Python:
  - pytest
  - ruff check .
  - mypy . when configured
- Node:
  - commands from package.json
- Rust:
  - cargo test
  - cargo clippy

### Verification behavior

- structured Verdict
- argv-based execution
- per-command timeout
- process-group kill
- head + tail output truncation
- one retry for suspected flaky verification

### Done when

Verification returns correct structured results for Python, Node, and Rust toy repositories.

## M5 — CodingAgentLoop

Build the real loop.

### Components

**CodingTask** tracks:

- task id
- goal
- repository
- plan
- current step
- attempts
- status
- artifacts
- verdicts
- budgets

**Planner**

- Input: goal, repository context
- Output:
  - up to 7 steps
  - each step has a description and acceptance criteria
- May return an impossible-task result.

**Actor**

Executes a step through the approved coding tools in a bounded inner loop.

**Verifier**

Runs after every changing step.

**Reflector**

- Receives:
  - failed step
  - attempt number
  - verifier result
- Returns:
  - revised approach
  - or IMPOSSIBLE

### Done when

The loop succeeds on at least 3 hand-written tasks, including one where:

- attempt 1 → verification failure
- attempt 2 → corrected implementation → verification pass

## M6 — Persistence + Git Safety + Task Approval

### Work

- Persist task state in SQLite.
- Run each coding task on `guru/<task_id>`.
- Extend capability constraints with repository/path scope.
- Add task-scoped approval covering:
  - repository
  - branch
  - allowed commands
  - budget
- Never auto-commit.

### Done when

- restarting after interruption preserves task state
- the main branch remains untouched
- one approval covers the approved task scope
- changing scope requires new approval

## M7 — CLI

Add `guru code "..."` with the following options:

- `--repo`
- `--dry-run`
- `--max-steps`

The CLI must work without:

- Qt
- Gemini Live
- voice

It should stream useful progress to stdout.

### Done when

The coding agent can be debugged entirely from the CLI.

## M8 — Benchmark

Run five canonical tasks against a throwaway repository:

- Add a function + test.
- Fix a failing test.
- Rename a function used in three files.
- Add a CLI flag.
- Add GET /health + test.

Target: **≥ 4 / 5**

Record every failure and its actual cause.

### Done when

There is a reproducible benchmark result rather than a one-time success.

## M9 — Assistant Integration

Extend the existing delegation mechanism:

```text
delegate_to_agent(
    task,
    repo_path=None,
    mode="coding"
)
```

Do not create a separate redundant coding-delegation system.

Assistant-visible events should be limited to:

- STARTED
- APPROVAL_REQUIRED
- BLOCKED
- DONE

The assistant provides milestone narration rather than narrating every tool call.

### Done when

```text
voice request
→ delegate coding task
→ agent executes
→ tests pass
→ assistant reports result
```

without execution chatter.

## M10 — Model Router

Only after the benchmark exists.

Start with a simple configuration-driven router:

```text
planning   → Gemini
coding     → Ollama / qwen2.5-coder
reflection → Gemini
```

Add fallback behavior.

Benchmark models on the canonical tasks before making permanent routing decisions.

### Done when

The router is configuration-driven and there is benchmark evidence supporting the model assignments.

## M11 — Sandbox

Run coding-agent commands through a stronger OS-level sandbox.

### Initial target

- bubblewrap
- network disabled by default
- filesystem restricted to the task worktree
- explicit opt-in escape hatch

### Done when

The agent cannot:

- access the network by default
- write outside the worktree
- modify arbitrary $HOME files

## Do Not Build Before M8 Benchmark

Do not spend time on:

- Anthropic / OpenRouter / additional providers
- learned model routing
- plugin system
- multi-agent swarms
- vector databases / embeddings / elaborate memory
- browser automation inside the coding agent
- vision inside the coding agent
- Docker/container tooling
- mobile/remote/web UI
- UI redesign
- voice redesign
- F2/F3 improvements
- new desktop capabilities

The focus remains:

A verified coding loop that reliably converts requests into passing, reviewable repository changes.

## Development Process

For every milestone:

1. Select one milestone
2. Inspect the current implementation
3. Plan the smallest change
4. Implement
5. Run tests
6. Review the diff
7. Fix issues
8. Run tests again
9. Commit
10. Mark the milestone complete
11. Move to the next milestone

Never skip the verification step.

Never mark a milestone complete because an AI claims it is complete.
