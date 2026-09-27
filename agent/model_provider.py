from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

import requests
from google import genai
from google.genai import types

from providers.ollama import OLLAMA_BASE_URL


@dataclass
class AgentFunctionCall:
    name: str
    arguments: Dict[str, Any]


@dataclass
class AgentResponse:
    text: str
    function_calls: List[AgentFunctionCall]


def _gemini_schema(schema: Dict[str, Any]):
    type_map = {
        "string": types.Type.STRING,
        "integer": types.Type.INTEGER,
        "number": types.Type.NUMBER,
        "boolean": types.Type.BOOLEAN,
        "object": types.Type.OBJECT,
        "array": types.Type.ARRAY,
    }
    schema_type = schema.get("type", "object")
    kwargs: Dict[str, Any] = {"type": type_map[schema_type]}
    if schema_type == "object":
        kwargs["properties"] = {
            name: _gemini_schema(prop)
            for name, prop in schema.get("properties", {}).items()
        }
        kwargs["required"] = schema.get("required", [])
    if schema_type == "array":
        kwargs["items"] = _gemini_schema(schema["items"])
    if "description" in schema:
        kwargs["description"] = schema["description"]
    return types.Schema(**kwargs)


class GeminiAgentSession:
    def __init__(
        self,
        model_id: str,
        system_instruction: str,
        tool_specs: Sequence[Any],
        history: Sequence[Dict[str, str]],
    ):
        declarations = [
            types.FunctionDeclaration(
                name=spec.name,
                description=spec.description,
                parameters=_gemini_schema(spec.input_schema),
            )
            for spec in tool_specs
        ]
        history_contents = [
            types.Content(
                role="model" if item["role"] == "assistant" else "user",
                parts=[types.Part(text=item["content"])],
            )
            for item in history
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
        # Keep the client alive for the entire chat session.
        # google-genai owns the underlying HTTP client here; letting this
        # local variable die can close the transport while chat is still used.
        self.client = genai.Client()
        config_kwargs = {
            "system_instruction": system_instruction,
            "temperature": 0.0,
        }
        if declarations:
            config_kwargs["tools"] = [types.Tool(function_declarations=declarations)]
        self.chat = self.client.chats.create(
            model=model_id,
            config=types.GenerateContentConfig(**config_kwargs),
            history=history_contents,
        )

    @staticmethod
    def _normalize(response: Any) -> AgentResponse:
        calls = [
            AgentFunctionCall(name=call.name, arguments=dict(call.args or {}))
            for call in (getattr(response, "function_calls", None) or [])
        ]
        return AgentResponse(text=getattr(response, "text", None) or "", function_calls=calls)

    def send_message(self, message: str) -> AgentResponse:
        return self._normalize(self.chat.send_message(message))

    def close(self):
        """Release the Gemini client after the runtime has finished using it."""
        self.client.close()

    def send_tool_results(
        self, calls: Sequence[AgentFunctionCall], results: Sequence[str]
    ) -> AgentResponse:
        parts = [
            types.Part.from_function_response(
                name=call.name, response={"output": result}
            )
            for call, result in zip(calls, results)
        ]
        return self._normalize(self.chat.send_message(parts))


class OllamaAgentSession:
    def __init__(
        self,
        model_id: str,
        system_instruction: str,
        tool_specs: Sequence[Any],
        history: Sequence[Dict[str, str]],
    ):
        self.model_id = model_id
        self.messages = [{"role": "system", "content": system_instruction}]
        self.messages.extend(
            {"role": item["role"], "content": item["content"]}
            for item in history
            if item.get("role") in {"user", "assistant"} and item.get("content")
        )
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.input_schema,
                },
            }
            for spec in tool_specs
        ]

    def _request(self) -> AgentResponse:
        payload = {
            "model": self.model_id,
            "messages": self.messages,
            "stream": False,
            "options": {"temperature": 0},
        }
        if self.tools:
            payload["tools"] = self.tools
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        message = response.json().get("message", {})
        self.messages.append(message)
        calls = [
            AgentFunctionCall(
                name=call["function"]["name"],
                arguments=call["function"].get("arguments") or {},
            )
            for call in message.get("tool_calls", [])
        ]
        return AgentResponse(text=message.get("content") or "", function_calls=calls)

    def send_message(self, message: str) -> AgentResponse:
        self.messages.append({"role": "user", "content": message})
        return self._request()

    def send_tool_results(
        self, calls: Sequence[AgentFunctionCall], results: Sequence[str]
    ) -> AgentResponse:
        for call, result in zip(calls, results):
            self.messages.append({
                "role": "tool",
                "tool_name": call.name,
                "content": result,
            })
        return self._request()

    def close(self):
        """Ollama uses per-request HTTP connections managed by requests."""
        return None


def create_agent_session(
    model_id: str,
    system_instruction: str,
    tool_specs: Sequence[Any],
    history: Sequence[Dict[str, str]],
):
    if model_id.startswith("gemini"):
        return GeminiAgentSession(model_id, system_instruction, tool_specs, history)
    return OllamaAgentSession(model_id, system_instruction, tool_specs, history)
