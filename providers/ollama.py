
import requests
import os
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

def get_ollama_models():
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        return [item.get("name") for item in response.json().get("models", []) if item.get("name")]
    except:
        return []
    