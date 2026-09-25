# Guru Agent

A local-first personal desktop AI assistant that blends:

- Ollama-powered local reasoning
- Gemini cloud fallback for vision and research tasks
- desktop actions for browsing, launching apps, and handling files
- a chat workspace with session memory and approval-aware agent actions

The goal is to create a practical, privacy-aware assistant that can help with day-to-day desktop work without forcing everything through a cloud service.

## What this project is trying to become

This app is designed as a personal AI workspace with a human-in-the-loop pattern:

1. Quick local tasks stay fast and simple.
2. Riskier actions require approval before they run.
3. Voice and visual input are treated as first-class inputs.
4. The assistant can reason locally, inspect the screen, and route deeper work through a tool or agent layer.

In plain terms, we want a desktop assistant that can:

- answer local questions using Ollama
- use Gemini when a stronger vision or cloud-backed answer is needed
- open websites, apps, files, and system controls with approval where appropriate
- listen through a mic and understand what the user says
- inspect the screen and describe what is visible
- follow a workflow that is transparent and safe

## Current direction

We are building the assistant in layers:

- chat and session UI
- orchestration layer for deciding route vs local tool vs agent work
- assistant features for voice, screen, and desktop automation
- approval-based action safety

The current milestone is to make the interface feel like a real personal assistant rather than a text-only demo.

## Quick start

1. Install Python dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
2. Start Ollama locally and pull a model, for example:
   ```bash
   ollama pull qwen2.5-coder
   ```
3. Copy `.env.example` to `.env` and set your Gemini API key if you want image analysis and cloud fallback enabled.
4. Run the app:
   ```bash
   python main.py
   ```

## Local model note

The app prefers local Ollama models when available. Gemini is used for cloud fallback and image-based analysis when `GEMINI_API_KEY` is configured.

## Project structure

- `main.py` launches the desktop app
- `ui_scratchpad.py` contains the main UI and chat flow
- `db.py` stores sessions and messages in SQLite
- `cat_talker/orchestrator.py` decides whether a request should be local, desktop-driven, or delegated
- `cat_talker/llm_router.py` handles model routing and streaming
- `cat_talker/desktop_actions.py` contains direct desktop actions like open app, website, volume, brightness
- `cat_talker/assistant_features.py` covers voice input, screen capture, and image analysis
- `cat_talker/agentic_tools.py` handles file read/search/write and pending approval actions

## Roadmap

### Phase 1: working local desktop assistant

- [x] app starts and loads a chat UI
- [x] local Ollama routing works
- [x] Gemini fallback and API key flow exists
- [x] desktop action routing is in place
- [x] basic approval flow exists

### Phase 2: richer assistant behaviors

- [x] push-to-talk-style voice capture flow
- [x] screen snapshot and screen description workflow
- [x] approval modal for direct actions
- [ ] smoother hold-to-talk mic UX with live recording state
- [ ] stronger active-window capture and analysis mode
- [ ] more polished desktop automation actions

### Phase 3: personal productivity focus

- [ ] active-window target selection
- [ ] region-based screenshot inspection
- [ ] smarter agent actions with safer approval UX
- [ ] better workflow for reading docs, code, and file context
- [ ] more advanced voice + screen assistant loops

## Todo list

- [x] basic app startup and model routing
- [x] direct action execution pipeline
- [x] assistant + agent handoff flow
- [x] voice input and screen analysis integration
- [ ] live recording indicator for mic input
- [ ] stronger active-window screen analysis mode
- [ ] action confirmation polish for multi-step workflows
- [ ] expand desktop automation coverage
- [ ] improve local-first reliability and fallback messaging

## Notes

This project is intentionally designed to be local-first and transparent. The assistant should feel like a helper that is present on the desktop, not a mysterious backend-only chatbot.

The next upgrades are aimed at making it feel like a real personal assistant:

- hold-to-talk voice interaction
- focused active-window analysis
- better approval UX before sensitive actions
- more useful desktop command understanding
