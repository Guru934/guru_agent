
from providers.ollama import get_ollama_models
from providers.gemini import get_gemini_models

def get_installed_models():
    models = get_ollama_models()
    models.extend(get_gemini_models())
    if not models:
        models = ["qwen-6gb:latest"]
    return models
