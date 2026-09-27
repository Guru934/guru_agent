# Guru Agent Architectural Roadmap

This document outlines the strategic phases to evolve the `guru_agent` from a heuristic-scripted prototype into a robust, secure, and fully event-driven AI agent. 

> The problems listed below record the original roadmap baseline and may no longer describe the current code. See [update.md](./update.md) and [PROJECT_STATUS.md](./PROJECT_STATUS.md) for the verified implementation status and remaining hardening work.

## The Core Problems to Solve
1. **Security Boundaries are Leaky:** `agent/policy.py` checks things superficially, but parts of the codebase circumvent it by executing `execute_shell` or `write_file` directly.
2. **Missing Agent Loop:** We rely on a "heavy agent" macro-loop instead of a strict atomic `PLAN -> ACT -> OBSERVE -> DECIDE` state machine.
3. **Planner is Heuristic:** `agent/planner.py` uses keyword triggers (`if "youtube" in text`) instead of generating structural plans.
4. **Bifurcated Event Architecture:** Gemini Live (voice) uses direct tools, bypassing the main orchestration pipeline used for terminal/text inputs.
5. **Implicit Surveillance:** Gemini Live boots auto-magically on app load, violating privacy UX. Microphone loops should require explicit user enablement.
6. **State vs Source Mixing:** `handoff_status.txt` lives in the project repo instead of `~/.local/share/guru_agent/`. 
7. **Polling vs Events:** `main_window.py` currently polls text files for IPC instead of consuming a true `AgentEvent` memory layer.
8. **Missing Tool Schema Validation:** Tool executions are missing typed input validations (e.g., via Pydantic).
9. **Unrestricted OS Access:** Agents can `read_file("~/.ssh/id_rsa")`. We need a `Workspace` confinement policy.
10. **Command Execution Policy:** Shell execution needs to be strictly classified into `SAFE`, `APPROVAL`, and `BLOCKED` tiers.
11. **Transactional Approvals:** Instead of approving textual UI prompts, OS approvals should grant execute permissions upon the exact programmatic `Task` instance.
12. **Missing Task IDs:** Multi-step agent behavior becomes hard to debug without global IDs connecting parent and child jobs.
13. **Vulnerable Test Suite:** We need deterministic unit tests to ensure that regressions do not open OS vulnerability holes (e.g., testing `safe_mode=True` blocks terminal execution).

---

## The Execution Plan

### Phase 0: Freeze Features
No external tools, no calendar plugins, no browser-agents, and no extra UI features until the core architecture below is entirely established.

### Phase 1: Unified Tool Execution
**Goal:** Create a single choke-point for all tool execution.
**Tasks:**
- Create `agent/executor.py`, `agent/approvals.py`, and `agent/events.py`.
- Ensure all OS actions strictly flow through: `Executor -> Policy -> Approval -> Tool`.
- Replace the `handoff_status.txt` file logging with an in-memory `AgentEvent` payload publisher.

### Phase 2: Real Agent Loop
**Goal:** Dismantle the prototype script loop.
**Tasks:**
- Establish `AgentRuntime` supporting step limits, cancellation, and continuous `observation` ingestion.
- The new core loop: `while not state.completed: plan -> act -> observe`.

### Phase 3: Structured Tool Calling
**Goal:** Drop XML parsing (`<bash>...</bash>`).
**Tasks:**
- Enforce structured tool-calling endpoints. Every tool must have a strict `name`, `description`, `input_schema` (Pydantic), and `risk_level`.

### Phase 4: Workspace + Security Model
**Goal:** File & command sandboxing.
**Tasks:**
- Implement `WORKSPACE_ROOT` confinement (e.g. `~/guru_projects/`).
- Hardcode shell policy categorizations (`ls` = safe; `rm -rf /` = blocked; `npm install` = approval).

### Phase 5: Voice as Just Another Input Channel
**Goal:** Unify Gemini Live with textual logic.
**Tasks:**
- Convert Gemini live payload streams into standard `AgentRequest` objects passed into the main `AgentRuntime`.
- Disable automatic voice startup at launch.

### Phase 6: Observability
**Goal:** Better UI insight.
**Tasks:**
- Implement an agent "Task Panel" in the PyQt UI replacing unstructured event queues, tracking exact task sequences and their completion statuses visually.

### Phase 7: Evaluation Suite
**Goal:** Prove the agent actually works properly.
**Tasks:**
- Implement ~50 deterministic execution tests mimicking edge cases (e.g., workspace escape attempt, rejection handling, token usage).

### Phase 8: Advanced Capabilities
- Add advanced providers (RAG, long-term memory, browsers). Only to be touched when Phases 1-7 are concluded.

---

### Target Architecture Schematic
```text
Keyboard \        
Voice ----> [ AgentRequest ] 
Vision   /            |
                      v
             [ Agent Runtime ] (plan/act/observe)
                      |
             [ Tool Registry ]
                      |
             [ Policy Engine ]
                  /       \
           Allowed     Approval required
                 \        /
            [ Tool Executor ]
                  / | \
           Filesystem Shell Desktop
```
