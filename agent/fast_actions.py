from dataclasses import dataclass
import re
from urllib.parse import urlparse


@dataclass(frozen=True)
class FastAction:
    tool_name: str
    arguments: dict


_APP_ALIASES = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "chromium": "chromium",
    "brave": "brave",
    "brave browser": "brave",
    "firefox": "firefox",
    "code": "code",
    "vs code": "code",
    "vscode": "vscode",
    "terminal": "terminal",
    "kitty": "terminal",
    "calculator": "calculator",
    "notepad": "notepad",
}


_SITE_ALIASES = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "github": "https://github.com",
    "spotify": "https://spotify.com",
    "netflix": "https://netflix.com",
}


def _number_in(text: str):
    match = re.search(r"(?<!\d)(\d{1,3})(?:\s*%|\b)", text)
    if not match:
        return None
    value = int(match.group(1))
    return value if 0 <= value <= 100 else None


def resolve_fast_action(text: str):
    """Resolve a small, deterministic desktop command into a granular tool call.

    Returns None for questions and complex instructions so they continue through
    the normal AgentRuntime model/tool loop.
    """
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not normalized:
        return None

    # Do not turn ordinary questions containing these words into OS actions.
    if re.match(r"^(what|why|how|who|when|where|explain|tell me|can you explain|is|are)\b", normalized):
        return None

    # Volume controls.
    if re.search(r"\b(mute|silence)\b", normalized):
        return FastAction("set_volume", {"level_percent": 0})
    if re.search(r"\b(max(?:imize|imum)?|full|100)\b.*\b(volume|sound)\b", normalized):
        return FastAction("set_volume", {"level_percent": 100})
    if re.search(r"\b(volume|sound)\b.*\b(max(?:imize|imum)?|full|100)\b", normalized):
        return FastAction("set_volume", {"level_percent": 100})
    if re.search(r"\b(set|turn|change|put|make|adjust)\b.*\b(volume|sound)\b", normalized):
        value = _number_in(normalized)
        if value is not None:
            return FastAction("set_volume", {"level_percent": value})

    # Brightness controls.
    if re.search(r"\b(max(?:imize|imum)?|full|100)\b.*\b(brightness|screen brightness)\b", normalized):
        return FastAction("set_brightness", {"level_percent": 100})
    if re.search(r"\b(brightness|screen brightness)\b.*\b(max(?:imize|imum)?|full|100)\b", normalized):
        return FastAction("set_brightness", {"level_percent": 100})
    if re.search(r"\b(set|turn|change|put|make|adjust)\b.*\bbrightness\b", normalized):
        value = _number_in(normalized)
        if value is not None:
            return FastAction("set_brightness", {"level_percent": value})

    # Play a specific thing on YouTube.
    play_match = re.match(r"^(?:play|put on)\s+(.+?)(?:\s+on\s+youtube)?$", normalized)
    if play_match and "youtube" in normalized:
        query = play_match.group(1).strip()
        query = re.sub(r"\s+on\s+youtube$", "", query).strip()
        if query:
            return FastAction("search_and_play_youtube", {"query": query})

    # Known websites.
    open_match = re.match(r"^(?:open|visit|go to|navigate to)\s+(.+)$", normalized)
    if open_match:
        target = open_match.group(1).strip()
        target = re.sub(r"^the\s+", "", target)
        if target in _SITE_ALIASES:
            return FastAction("open_website", {"url": _SITE_ALIASES[target]})
        if target.startswith(("http://", "https://")):
            parsed = urlparse(target)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return FastAction("open_website", {"url": target})
        if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}(?:/[^ ]*)?", target):
            return FastAction("open_website", {"url": "https://" + target})

        # Known desktop applications.
        app_name = target
        app_name = re.sub(r"\s+application$", "", app_name)
        if app_name.endswith(" app"):
            app_name = app_name[:-4].strip()
        if app_name in {"browser", "web browser"}:
            app_name = "chrome"
        if app_name in _APP_ALIASES:
            return FastAction("open_application", {"app_name": _APP_ALIASES[app_name]})

    # Direct "open <app>" commands without the website grammar.
    app_match = re.match(r"^(?:launch|start|open)\s+(.+)$", normalized)
    if app_match:
        target = re.sub(r"\s+application$", "", app_match.group(1).strip())
        if target.endswith(" app"):
            target = target[:-4].strip()
        if target in {"browser", "web browser"}:
            target = "chrome"
        if target in _APP_ALIASES:
            return FastAction("open_application", {"app_name": _APP_ALIASES[target]})

    return None
