
import os
try:
    from google import genai
except ImportError:
    genai = None

def gemini_stream(model_id, messages):
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = "\n\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages)
    response = client.models.generate_content_stream(model=model_id, contents=prompt)
    for chunk in response:
        if getattr(chunk, "text", None):
            yield chunk.text
            
def get_gemini_models():
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if GEMINI_API_KEY:
        return ["gemini-2.0-flash", "gemini-2.5-flash"]
    return []
    