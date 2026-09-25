import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

try:
    from faster_whisper import WhisperModel
except Exception:  # pragma: no cover - optional at runtime
    WhisperModel = None

try:
    import mss
    from PIL import Image
except Exception:  # pragma: no cover - optional at runtime
    mss = None
    Image = None

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:  # pragma: no cover - optional at runtime
    genai = None
    genai_types = None


def build_approval_message(action_name: str, action_description: str, risk_level: str = "low") -> str:
    """Return a concise confirmation prompt for desktop or tool-based actions."""
    return (
        f"Action: {action_name}\n"
        f"Details: {action_description}\n"
        f"Risk: {risk_level}\n\n"
        "Approve this action? [Y/N]"
    )


def voice_input_status() -> str:
    """Return the current local voice/transcription status."""
    parts = []
    if shutil.which("ffmpeg"):
        parts.append("ffmpeg available")
    if shutil.which("arecord"):
        parts.append("arecord available")
    if shutil.which("sox"):
        parts.append("sox available")
    if WhisperModel is not None:
        parts.append("local Whisper STT ready")
    if not parts:
        return "Voice input is not configured yet; install ffmpeg and faster-whisper or connect a local speech backend."
    return "Voice input is ready locally: " + ", ".join(parts) + "."


def _record_audio_to_wav(record_seconds: int = 5, output_path: Optional[str] = None) -> Optional[str]:
    """Record a short waveform using the best available local tool."""
    if output_path is None:
        output_path = str(Path(tempfile.gettempdir()) / "assistant_voice_capture.wav")

    if shutil.which("arecord"):
        cmd = ["arecord", "-D", "default", "-f", "cd", "-t", "wav", "-d", str(record_seconds), output_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0 and Path(output_path).exists():
            return output_path

    if shutil.which("ffmpeg"):
        cmd = ["ffmpeg", "-y", "-f", "alsa", "-i", "default", "-t", str(record_seconds), output_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0 and Path(output_path).exists():
            return output_path

    if shutil.which("sox"):
        cmd = ["sox", "-d", output_path, "trim", "0", str(record_seconds)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0 and Path(output_path).exists():
            return output_path

    return None


def transcribe_audio_file(audio_path: str) -> str:
    """Transcribe a saved audio file with local Whisper when available."""
    if WhisperModel is None:
        return "Speech-to-text backend is not available yet. Install faster-whisper and a microphone capture tool to enable live voice input."
    if not audio_path or not Path(audio_path).exists():
        return "No valid recording file was captured for transcription."

    try:
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(audio_path, beam_size=5)
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        if text:
            return text
        return "Voice input captured, but no clear speech was detected in the recording."
    except Exception as exc:
        return f"Voice transcription failed: {exc}"


def transcribe_audio_from_microphone(record_seconds: int = 5) -> str:
    """Record a short clip and transcribe it with local Whisper when available."""
    audio_path = _record_audio_to_wav(record_seconds=record_seconds)
    if not audio_path:
        return "No microphone capture backend is available right now. Voice input is configured for a local mic and ffmpeg/arecord pipeline."
    return transcribe_audio_file(audio_path)


def capture_screen_snapshot(monitor: Optional[str] = None) -> str:
    """Capture a screen image using an actual local backend when available."""
    screenshot_dir = Path.home() / "Pictures" / "Screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    target = screenshot_dir / "assistant_snapshot.png"

    try:
        if mss is not None:
            with mss.MSS() as sct:
                monitor_id = 0
                if monitor and monitor.isdigit():
                    monitor_id = int(monitor)
                try:
                    sct.shot(output=str(target), monitor=monitor_id)
                except Exception:
                    sct.shot(output=str(target))
            if target.exists():
                return str(target)
    except Exception:
        pass

    try:
        if shutil.which("grim"):
            cmd = ["grim", str(target)]
            if monitor:
                cmd.extend(["-o", monitor])
            subprocess.run(cmd, check=False, capture_output=True, text=True)
            if target.exists():
                return str(target)

        if shutil.which("scrot"):
            subprocess.run(["scrot", str(target)], check=False, capture_output=True, text=True)
            if target.exists():
                return str(target)

        if shutil.which("import"):
            subprocess.run(["import", "-window", "root", str(target)], check=False, capture_output=True, text=True)
            if target.exists():
                return str(target)

        return "No screen capture backend is available; local vision capture is ready to be enabled on a desktop with a screenshot utility."
    except Exception:
        return "No screen capture backend is available; local vision capture is ready to be enabled on a desktop with a screenshot utility."


def capture_active_window_snapshot() -> str:
    """Attempt to capture the current focused application window for local analysis."""
    screenshot_dir = Path.home() / "Pictures" / "Screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    target = screenshot_dir / "assistant_active_window.png"

    try:
        if shutil.which("xdotool"):
            window_id = subprocess.run(
                ["xdotool", "getactivewindow"],
                check=False,
                capture_output=True,
                text=True,
            )
            window_text = (window_id.stdout or "").strip()
            if window_text:
                if shutil.which("import"):
                    result = subprocess.run(
                        ["import", "-window", window_text, str(target)],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0 and target.exists():
                        return str(target)

        if shutil.which("import"):
            result = subprocess.run(["import", "-window", "root", str(target)], check=False, capture_output=True, text=True)
            if result.returncode == 0 and target.exists():
                return str(target)

        if shutil.which("grim"):
            result = subprocess.run(["grim", str(target)], check=False, capture_output=True, text=True)
            if result.returncode == 0 and target.exists():
                return str(target)

        return "No active-window capture backend is available right now; full-screen capture remains as a fallback."
    except Exception:
        return "No active-window capture backend is available right now; full-screen capture remains as a fallback."


def _extract_text_from_response(response) -> str:
    if response is None:
        return ""
    if hasattr(response, "text") and response.text:
        return str(response.text)
    if hasattr(response, "candidates"):
        parts = []
        for candidate in response.candidates:
            content = getattr(candidate, "content", None)
            if content is None:
                continue
            if hasattr(content, "parts"):
                for part in content.parts:
                    if hasattr(part, "text") and part.text:
                        parts.append(part.text)
        if parts:
            return "\n".join(parts)
    if isinstance(response, dict):
        return str(response.get("text") or response.get("content") or response)
    return str(response)


def analyze_screen_image(image_path: str, question: str = "Describe the visible screen and note important UI elements or content.") -> str:
    """Use Gemini to analyze a captured image when a valid API key is available."""
    if not image_path or not Path(image_path).exists():
        return "No valid image file was provided for screen analysis."

    if genai is None or genai_types is None:
        return "Gemini image analysis is unavailable because the google-genai package is not installed."

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "Gemini image analysis is unavailable because GEMINI_API_KEY is missing."

    try:
        client = genai.Client(api_key=api_key)
        image_bytes = Path(image_path).read_bytes()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                genai_types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                question,
            ],
        )
        text = _extract_text_from_response(response)
        if text.strip():
            return text.strip()
        return "Gemini processed the image, but it returned no readable description."
    except Exception as exc:
        return f"Screen analysis failed: {exc}"


def describe_current_screen(question: str = "Describe the visible screen and note key interface elements, text, and context.") -> str:
    """Capture and describe the current desktop screen using the local capture path and Gemini analysis when available."""
    snapshot = capture_screen_snapshot("primary")
    if not snapshot or not snapshot.startswith("/"):
        return snapshot or "No screen capture backend is available; unable to describe the current screen."

    return analyze_screen_image(snapshot, question)


def describe_active_window(question: str = "Extract and structure visible text using Markdown. Ignore blank space, and identify the primary context and core interactive elements of the active window.") -> str:
    """Capture and describe the focused application window rather than the full desktop."""
    snapshot = capture_active_window_snapshot()
    if not snapshot or not snapshot.startswith("/"):
        return snapshot or "No active-window capture was possible, so full-screen analysis remains the fallback."

    return analyze_screen_image(snapshot, question)


def summarize_action_plan(action_name: str, description: str) -> str:
    """Provide a compact status summary for approval flows."""
    risk = "low" if action_name in {"open_website", "read_file", "open_app"} else "medium"
    return build_approval_message(action_name, description, risk_level=risk)
