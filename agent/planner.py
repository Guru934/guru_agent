from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal
import re


from agent.state import OrchestrationPlan

class AgentOrchestrator:
    """Small orchestration layer to route user requests.

    - direct: answer directly with the current model
    - delegate: request tool / agent execution for file/search/shell work
    """

    def __init__(self, default_model: str = "qwen2.5-coder", safe_mode: bool = False):
        self.safe_mode = safe_mode
        self.default_model = default_model

    def build_context_instruction(self, plan: OrchestrationPlan) -> str:
        if plan.route == "direct":
            return "You are acting as a personal assistant. Keep the answer concise, practical, and helpful."

        if plan.route == "desktop_action":
            return (
                "You are acting as the desktop assistant. Perform the requested local desktop action directly, "
                "such as opening a website, app, media, or controlling system settings. Keep it fast and minimal."
            )

        tool_hint = ", ".join(plan.tool_calls) if plan.tool_calls else "general agent work"
        return (
            f"You are operating in agent mode. This request is delegated for tool-assisted work. "
            f"Preferred model: {plan.preferred_model}. "
            f"Focus on: {tool_hint}. "
            "Use local tools cautiously, prefer safe file reads and explicit confirmations before destructive actions."
        )

    def decide(self, user_input: str) -> OrchestrationPlan:
        text = (user_input or "").strip()
        if not text:
            return OrchestrationPlan(route="direct", preferred_model=self.default_model, tool_calls=[], reason="Empty input")

        lowered = text.lower()

        if any(keyword in lowered for keyword in [
            "open youtube", "play music", "open website", "open chrome", "launch", "open app",
            "set volume", "volume", "brightness", "mute", "open browser", "search youtube",
            "play a song", "play music", "open vscode", "open terminal", "start app"
        ]):
            return OrchestrationPlan(
                route="desktop_action",
                preferred_model=self.default_model,
                tool_calls=["desktop_control"],
                reason="This is a direct desktop or media action and should not trigger the heavier agent workflow.",
            )

        if any(keyword in lowered for keyword in [
            "search", "read", "file", "folder", "grep", "find", "shell",
            "command", "edit", "write", "open", "review", "analyze project",
            "look through", "check the code", "inspect the file"
        ]):
            tool_calls = []
            if any(k in lowered for k in ["search", "grep", "find", "look through", "inspect"]):
                tool_calls.append("search")
            if any(k in lowered for k in ["read", "file", "open", "review", "check the code", "inspect the file"]):
                tool_calls.append("read_file")
            if not self.safe_mode:
                if any(k in lowered for k in ["write", "edit", "update", "modify"]):
                    tool_calls.append("write_file")
                if any(k in lowered for k in ["command", "bash", "shell", "run"]):
                    tool_calls.append("bash")
            return OrchestrationPlan(
                route="delegate",
                preferred_model=self._choose_model_for_task(lowered),
                tool_calls=tool_calls,
                reason="User request requires codebase work or local system actions.",
            )

        if any(keyword in lowered for keyword in ["latest", "recent", "news", "live", "current", "trend", "research", "market", "today"]):
            return OrchestrationPlan(
                route="delegate",
                preferred_model="gemini-2.5-flash",
                tool_calls=[],
                reason="Current-world or research-style request is better handled with cloud model access.",
            )

        if self._looks_like_simple_question(lowered):
            return OrchestrationPlan(
                route="direct",
                preferred_model=self.default_model,
                tool_calls=[],
                reason="Direct Q&A with no files or system actions needed.",
            )

        return OrchestrationPlan(
            route="delegate",
            preferred_model=self._choose_model_for_task(lowered),
            tool_calls=[],
            reason="Task likely needs reasoning or tool usage.",
        )

    def _choose_model_for_task(self, text: str) -> str:
        if any(keyword in text for keyword in ["latest", "trend", "news", "research", "market", "current", "summarize recent", "world"]):
            return "gemini-2.5-flash"
        return self.default_model

    def _looks_like_simple_question(self, text: str) -> bool:
        simple_patterns = [
            "what is ",
            "who is ",
            "when is ",
            "where is ",
            "why is ",
            "how is ",
            "what are ",
            "can you explain ",
            "tell me about ",
            "define ",
        ]
        if any(p in text for p in simple_patterns):
            return True

        if re.fullmatch(r"[a-z0-9 ,.?;:!'\"]+", text) and len(text.split()) <= 18:
            return True

        return False
