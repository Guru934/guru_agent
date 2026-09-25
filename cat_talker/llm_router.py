import json
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List

import requests


def _load_env_file():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

try:
    from google import genai
except Exception:  # pragma: no cover
    genai = None


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def _normalize_role(role: str) -> str:
    if role == "assistant":
        return "assistant"
    if role == "user":
        return "user"
    return "user"


def get_ollama_models() -> List[str]:
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        response.raise_for_status()
        payload = response.json()
        models = []
        for item in payload.get("models", []):
            name = item.get("name")
            if name:
                models.append(name)
        return models
    except Exception:
        return []


def get_installed_models() -> List[str]:
    models: List[str] = []
    local_models = get_ollama_models()
    if local_models:
        models.extend(local_models)

    if GEMINI_API_KEY:
        models.extend([
            "gemini-2.0-flash",
            "gemini-2.5-flash",
        ])

    if not models:
        models = ["qwen-6gb:latest"]
    return models


def _ollama_stream(model_id: str, messages: List[Dict[str, str]]) -> Iterator[str]:
    payload = {
        "model": model_id,
        "messages": [{"role": _normalize_role(m.get("role", "user")), "content": m.get("content", "")} for m in messages],
        "stream": True,
    }
    try:
        response = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, stream=True, timeout=120)

        if not response.ok:
            try:
                error_msg = response.json().get("error", response.text)
            except Exception:
                error_msg = response.text
            raise RuntimeError(f"Ollama API Error ({response.status_code}): {error_msg}")

        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(f"Could not connect to Ollama at {OLLAMA_BASE_URL}. Is it running?")

    for line in response.iter_lines():
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = data.get("message", {})
        content = message.get("content")
        if content:
            yield content


def _gemini_stream(model_id: str, messages: List[Dict[str, str]]) -> Iterator[str]:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it in the shell or .env file.")
    if genai is None:
        raise RuntimeError("The google-genai package is not installed. Install it with pip install google-genai.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = "\n\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
    )
    response = client.models.generate_content_stream(model=model_id, contents=prompt)
    for chunk in response:
        text = getattr(chunk, "text", None)
        if text:
            yield text


def chat_completion_stream(model_id: str, messages: List[Dict[str, Any]]) -> Iterator[str]:
    if model_id.startswith("gemini"):
        yield from _gemini_stream(model_id, messages)
        return

    if not get_ollama_models():
        raise ConnectionError(
            "Could not connect to the Ollama server. Please ensure Ollama is running and accessible at http://127.0.0.1:11434."
        )

    yield from _ollama_stream(model_id, messages)


def simple_chat(model_id: str, user_text: str) -> str:
    return "".join(chat_completion_stream(model_id, [{"role": "user", "content": user_text}]))
