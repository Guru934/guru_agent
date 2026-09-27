
from providers.ollama import get_ollama_models, ollama_stream
from providers.gemini import get_gemini_models, gemini_stream

def get_installed_models():
    models = get_ollama_models()
    models.extend(get_gemini_models())
    if not models:
        models = ["qwen-6gb:latest"]
    return models

def chat_completion_stream(model_id, messages):
    if model_id.startswith("gemini"):
        yield from gemini_stream(model_id, messages)
    else:
        yield from ollama_stream(model_id, messages)
