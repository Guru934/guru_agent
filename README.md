# Guru Agent

Guru Agent is a local-first desktop AI assistant for Linux. It combines a
PyQt6 desktop application and Gemini Live voice conversation with a
policy-controlled agent runtime for working with tools and local repositories.

The long-term goal is to turn requests such as “fix this bug” into verified,
reviewable repository changes. That coding-agent loop is still under
development; see [Project status](#project-status) for what is implemented
today.

## What it does today

- Provides a desktop chat interface with Gemini Live voice support.
- Runs delegated tasks through `AssistantBridge`, `AgentRuntime`,
  `ToolExecutor`, `PolicyEngine`, and approval/capability checks.
- Lets you select a Git repository as the active project and persists that
  selection in the local SQLite database.
- Provides repository tools for listing and reading files, searching,
  exact-match edits, Git status/diff, and bounded command execution.
- Detects verification commands for Python, Node.js, and Rust repositories and
  returns structured results, including command output and retry information.
- Includes an early vertical-slice coding example and M5 task/role scaffolding.
  These are not yet the complete autonomous coding loop.

## Project status

The verified implementation status is tracked in
[PROJECT_STATUS.md](./PROJECT_STATUS.md); the planned milestones and acceptance
criteria are in [ROADMAP.md](./ROADMAP.md).

- **M0–M4:** marked complete in the project status, including repository
  awareness, coding tools, a limited vertical slice, and deterministic
  verification.
- **M5 — CodingAgentLoop:** in progress. The task data model and role-interface
  scaffolding exist, but the full plan/act/verify/reflect/retry loop is not
  implemented.
- **M6–M11:** planned; see the roadmap.

Do not treat a planned capability or an AI-generated completion claim as
implemented functionality. `PROJECT_STATUS.md` is the source of truth for
verified progress.

## Requirements

- Linux desktop environment with a graphical display (Wayland or X11).
- Python 3.11 or newer recommended.
- Gemini API key for Gemini-backed chat and voice features.
- Audio input/output hardware and working system audio support for voice.
- System libraries required by PyQt6, PyAudio, and the packages in
  `requirements.txt`. On Debian/Ubuntu, PyAudio may require the PortAudio
  development package to be installed before its Python package can be built.
- Optional local Ollama service for features configured to use a local model.

Screen capture and desktop integrations depend on available system tools and
the current desktop session.

## Installation

Clone the repository, then from its root create and activate a virtual
environment:

```bash
git clone https://github.com/Guru934/guru_agent.git
cd guru_agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Configure Gemini Live by creating a local `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` and set `GEMINI_API_KEY` to your own key. Keep `.env` private; it is
local configuration and must not be committed or shared. Optional model
settings include `OLLAMA_BASE_URL` and `HEAVY_AGENT_MODEL`; their defaults and
usage are defined by the application.

## Run

Start the desktop app from the repository root with the virtual environment
active:

```bash
python app.py
```

The repository also includes `launch_agent.sh`, a launcher configured for the
original `/home/guru/guru_agent` installation path. If you cloned the project
elsewhere, run `python app.py` directly or update the launcher path for your
installation.

## Select a project repository

Coding tools require an explicitly selected, valid Git repository. Select and
inspect it with the `guru` helper:

```bash
python guru project use ~/path/to/your/repository
python guru project show
```

The selected repository path is validated and persisted in the local SQLite
preferences database. Explicit task repository paths take precedence over the
saved selection. Coding work must not silently fall back to Guru Agent's own
source tree.

The `guru` helper currently provides project selection and inspection; a
general `guru code` command is **not** implemented yet.

## Security model

Tool execution is designed to pass through the existing execution and policy
boundary:

```text
ToolExecutor → PolicyEngine → approval / capability checks → registered tool
```

Project-aware operations are scoped to the selected project, and Guru Agent's
own source and local state have additional protections. Command execution uses
argument lists, bounded timeouts, and bounded output rather than shell-string
execution in the repository coding tools.

These controls are application-level policy and approval mechanisms, not an
OS-level sandbox. The stronger sandbox described in M11 is future work. Review
approval prompts before allowing actions, and use a disposable repository when
trying experimental coding features.

## Tests

Install pytest in the active virtual environment if it is not already
available, then run the suite:

```bash
python -m pip install pytest
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

The offscreen Qt setting is useful on headless machines and in CI. Some tests
may skip when optional tools or host capabilities (for example, Rust tooling or
hard-link creation) are unavailable. Refer to
[PROJECT_STATUS.md](./PROJECT_STATUS.md) for recorded verification results and
known limitations.

## Repository layout

| Path | Purpose |
| --- | --- |
| `app.py` | Desktop application entry point |
| `ui/` | PyQt6 interface, chat, audio, and approval dialogs |
| `agent/` | Runtime, assistant bridge, policy, approvals, tools, verifier, and coding scaffolding |
| `tools/` | Filesystem, shell, desktop, browser, and repository tools |
| `providers/` | Gemini and Ollama provider integrations |
| `memory/` | SQLite-backed history and project preferences |
| `tests/` | Automated tests, including milestone-focused coverage |
| `ARCHITECTURE_PLAN.md` | Architecture history and project planning notes |
| `PROJECT_STATUS.md` | Verified implementation status |
| `ROADMAP.md` | Planned milestones and acceptance criteria |
| `AGENTS.md` | Engineering and repository instructions |

## Development guidance

- Read [AGENTS.md](./AGENTS.md) before substantial changes.
- Work on one roadmap milestone at a time and keep status aligned with
  verifiable evidence.
- Preserve the `ToolExecutor` and `PolicyEngine` security boundary.
- Run relevant tests after changes and review the diff before committing.
- Do not mark planned functionality complete until its acceptance criteria
  have been verified.
