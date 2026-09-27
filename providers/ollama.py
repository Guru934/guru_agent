
import json, requests
import os
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

def get_ollama_models():
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        return [item.get("name") for item in response.json().get("models", []) if item.get("name")]
    except:
        return []

def ollama_stream(model_id, messages):
    payload = {"model": model_id, "messages": messages, "stream": True}
    response = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, stream=True, timeout=120)
    response.raise_for_status()
    for line in response.iter_lines():
        if line:
            data = json.loads(line)
            if content := data.get("message", {}).get("content"):
                yield content
    