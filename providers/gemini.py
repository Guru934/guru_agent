
import os


def get_gemini_models():
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if GEMINI_API_KEY:
        return ["gemini-2.0-flash", "gemini-2.5-flash"]
    return []
    