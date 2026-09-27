# Project Status - Phase 1 Completion

## What Was Done
1. **Architectural Restructuring**
   - Dismantled the massive 72 KB `ui_scratchpad.py` God Object into logically distinct UI components: `ui/main_window.py`, `ui/widgets.py`, `ui/chat_view.py`, `ui/sidebar.py`, and `ui/approval_dialog.py`.
   - Reorganized repository loosely coupled modules into their correct structured domains (`agent/`, `providers/`, `tools/`, `memory/`).
   - Cleaned up obsolete and duplicate patch files (e.g. `cat-talker` overlapping `cat_talker`, deprecated AST regex patch bots `patch_*.py`).

2. **Core Systems Stabilization**
   - Created a central `app.py` bootstrapper. Evaluates Wayland vs X11 configurations contextually and forces absolute paths instead of relative assumptions (fixing constant runtime lookup crashes).
   - Localized recursive DB table schema definitions to a single `init_db()` boot operation residing in `memory/sqlite.py`. Re-injected the missed `preferences` table that crashed prior launches.
   - Diagnosed API and dependency validation logic (`diagnostics.py`).
   - Fixed missing dependencies for CI pipelines (`libegl1 libs and xvfb for PyQt tests`) on GitHub Actions, mapped `PYTHONPATH` context, and fixed module pathings inside the unit tests.

3. **External Environment Handshakes Fixed** 
   - Dynamically remapped the global Linux shortcuts config (`~/.config/hypr/hyprland/keybinds.lua`) binding `F1` and `F3` to point seamlessly to the new `app.py` process instead of the legacy `main.py` entrypoint.
   - Explicitly loaded audio generation and screen capture libraries into `requirements.txt` (`mss`, `websockets`, `PyAudio`, `opencv-python`).

## What We Know About The Project
- It is a Python desktop-assistant system heavily interfacing via PyQt6 (`guru_agent`), designed tightly over an underlying Hyprland / Wayland Linux tiling window manager environment.
- It leverages various local and cloud LLM execution endpoints: Qwen natively via Ollama for local low-latency routing, and Gemini 2.5 Flash / Gemini Live for multimodal live-desktop monitoring and large research requests.
- It attempts to mimic native-OS behaviors like `capture_screen_snapshot`, voice recognition, execution of local bash scripts, and reading files—handling security via an Approval UI component.
- The `AgentOrchestrator` governs routing between simple Q&A directly, shell delegation, or cloud models.

## What Needs To Be Done (Future Phases)
To elevate this into a highly robust and functional digital assistant platform, the following areas require effort in future phases:

* **Security & Safe Sandboxing:** Direct arbitrary `bash` approvals are natively dangerous. Standardized OS confinement layers, strict AppArmor profiles, or isolated Docker routines need consideration so user data is shielded from runaway agent behaviors.
* **Component Communication Refactoring:** PyQt bindings still tightly couple the orchestrator to UI logic inside `main_window.py`. Moving towards a robust message bus / Event loops driven approach separating Backend logic completely from Frontend rendering.
* **Database & Memory Scaling:** `sqlite.py` works right now but acts generically. Context injection rules need logic bounds (context-window-size management, RAG integration, vector similarity lookups) because as the database expands, feeding entire chats endlessly into `tool_calls` crashes models context thresholds.
* **Provider Fault Tolerance:** Gemini Live and Ollama instances crash or disconnect ungracefully currently when rate limits or offline states trigger. We need exponential backoff logic and clear UX indications for fallback modes.
* **Full E2E Testing:** The current Unittest structure evaluates mocked outputs but lacks fully synthesized End-to-End browser/desktop verification tests (using Xvfb/Playwright hooks). 

## Strategic Roadmap
Detailed architectural analysis and step-by-step phased refactoring goals (Phases 0 through 8) intended to shift this project from a prototype into a robust secure agent are fully documented in [ARCHITECTURE_PLAN.md](ARCHITECTURE_PLAN.md).

### Phase 2 & 3 Update - ReAct Execution & Tool Schemas
- Dismantled the procedural "heavy agent" script from `agent/agent.py` and implemented a complete deterministic `AgentRuntime` loop matching standard ReAct patterns (`while not completed: plan -> act -> observe`).
- Abstracted the `ToolRegistry` to enforce `ToolSpec` schemas bridging structural tools directly down to Gemini's `FunctionDeclarations`, completely bypassing XML `<bash>` parsing vulnerabilities and locking execution signatures (Phase 3 completion).
- The `PolicyEngine` now reads the risk evaluation inherently off the `ToolSpec` definitions rather than hardcoding block rules locally, making expansion safe.
