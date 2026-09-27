import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request


def open_application(app_name: str) -> str:
    if not app_name:
        return "Error: No application name provided."
    app_name = app_name.lower().strip()
    mapping = {
        "brave": "brave-browser",
        "chrome": "google-chrome",
        "terminal": "gnome-terminal" if shutil.which("gnome-terminal") else "kitty",
        "calculator": "gnome-calculator" if shutil.which("gnome-calculator") else "kcalc",
        "notepad": "gedit" if shutil.which("gedit") else "mousepad",
        "code": "code" if shutil.which("code") else "vscode",
        "vscode": "code" if shutil.which("code") else "vscode",
    }
    executable = mapping.get(app_name, app_name)
    if not shutil.which(executable):
        return f"Error: '{executable}' application could not be found."
    try:
        subprocess.Popen([executable], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Successfully opened {app_name}."
    except Exception as exc:
        return f"Failed to open {app_name}. Exception: {str(exc)}"


def open_website(url: str) -> str:
    if not url:
        return "Error: No URL provided."
    clean_url = url.strip()
    if not clean_url.startswith("http"):
        clean_url = "https://" + clean_url
    try:
        if shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", clean_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Successfully opened website: {clean_url}"
        if shutil.which("brave-browser"):
            subprocess.Popen(["brave-browser", clean_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Opened website in brave: {clean_url}"
        return "Error: xdg-open not found to launch URL."
    except Exception as exc:
        return f"Failed to open website. Exception: {str(exc)}"


def open_file(path: str) -> str:
    target_path = os.path.expanduser(path)
    if not os.path.exists(target_path):
        return f"Error: File {target_path} does not exist"
    try:
        if shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", target_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Successfully opened file {target_path}"
        return "Error: xdg-open not found."
    except Exception as exc:
        return f"Failed to open file: {exc}"


def set_volume(level_percent: int) -> str:
    level_percent = max(0, min(100, int(level_percent)))
    try:
        if shutil.which("wpctl"):
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{level_percent}%"], check=True)
            return f"System volume set to {level_percent}%"
        return "Error: wpctl tool not found."
    except Exception as exc:
        return f"Error setting volume: {exc}"


def set_brightness(level_percent: int) -> str:
    level_percent = max(0, min(100, int(level_percent)))
    try:
        if shutil.which("brightnessctl"):
            subprocess.run(["brightnessctl", "set", f"{level_percent}%"], check=True)
            return f"System brightness set to {level_percent}%"
        return "Error: brightnessctl tool not found."
    except Exception as exc:
        return f"Error setting brightness: {exc}"


def get_clipboard() -> str:
    try:
        if shutil.which("wl-paste"):
            result = subprocess.run(["wl-paste"], capture_output=True, text=True, timeout=2)
            return result.stdout.strip()
        if shutil.which("xclip"):
            result = subprocess.run(["xclip", "-o", "-selection", "clipboard"], capture_output=True, text=True, timeout=2)
            return result.stdout.strip()
        return "Error: No clipboard utility found."
    except Exception as exc:
        return f"Error accessing clipboard: {str(exc)}"


def search_and_play_youtube(query: str) -> str:
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.youtube.com/results?search_query={encoded_query}"
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            html = response.read().decode("utf-8")
        video_ids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", html)
        if not video_ids:
            return open_website(url)
        return open_website(f"https://www.youtube.com/watch?v={video_ids[0]}")
    except Exception as exc:
        return f"Failed to search and play YouTube: {exc}"


def handle_desktop_action(text: str) -> str:
    text = (text or "").strip()
    lowered = text.lower()

    if "youtube" in lowered or "music" in lowered or "play" in lowered and "youtube" in lowered:
        query = re.sub(r"(?i)^(open|play|search|for)\s+", "", text)
        query = re.sub(r"(?i)\s*(youtube|music)\s*", "", query).strip()
        if not query:
            query = "popular music"
        return search_and_play_youtube(query)

    if any(k in lowered for k in ["open website", "open browser", "visit ", "go to "]):
        target = text
        if "go to" in lowered:
            target = text.split("go to", 1)[1].strip()
        elif "open website" in lowered:
            target = text.split("open website", 1)[1].strip()
        elif "visit" in lowered:
            target = text.split("visit", 1)[1].strip()
        return open_website(target)

    if "open " in lowered and "app" not in lowered and "website" not in lowered and "file" not in lowered and "youtube" not in lowered:
        target = text.lower().replace("open ", "", 1).strip()
        if target:
            return open_application(target)

    if any(k in lowered for k in ["set volume", "volume"]):
        match = re.search(r"(\d+)", text)
        value = match.group(1) if match else 50
        return set_volume(int(value))

    if "brightness" in lowered:
        match = re.search(r"(\d+)", text)
        value = match.group(1) if match else 50
        return set_brightness(int(value))

    if "open file" in lowered or "open " in lowered and "." in lowered:
        path = text.replace("open file", "", 1).replace("open ", "", 1).strip()
        return open_file(path)

    return f"Desktop action recognized, but no direct handler matched: {text}"
