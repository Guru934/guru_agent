# Project Status

## Current State

Phases 1–6 have meaningful implementation, but their intended guarantees still require hardening and integration. They must not be marked complete merely because runtime, policy, executor, and event modules exist. Phase 7 is deferred until the Phase 1–6 entry criteria in [update.md](./update.md) are met.

The current application routes keyboard messages and transcribed voice messages through `AgentRuntime`. Tool schemas are provider-independent and validated before policy evaluation. The executor is the central path for registered agent tools, including desktop actions.

## Security Boundaries

- File tools enforce configured workspace roots, including resolving symlinks before access.
- Shell commands outside the restricted read-only allowlist require explicit approval while safe mode is enabled. Disabling safe mode explicitly allows non-blocked commands.
- Shell execution has a fixed working directory, filtered environment, timeout, and output cap.
- **User approval is not filesystem isolation. A non-allowlisted shell command permitted with safe mode off, or approved while safe mode is on, can still access files outside the workspace. This implementation is not suitable for unattended execution without stronger OS-level sandboxing.**
- Security audit records avoid logging file contents or raw command/query text; audit write failure denies tool execution.

## Validation

Core tests cover schema validation, shell policy boundaries, approval timeout and cancellation, worker-thread execution after approval, and runtime lifecycle. CI and broader project tests still need to pass before Phase 7 starts.

## Roadmap

1. Complete and verify Phase 1–6 hardening and runtime integration.
2. Start Phase 7 evaluations only when the Phase 1–6 entry criteria are satisfied.
3. Begin Phase 8 plugin infrastructure afterward.

See [ARCHITECTURE_PLAN.md](./ARCHITECTURE_PLAN.md) for the broader architecture roadmap.
