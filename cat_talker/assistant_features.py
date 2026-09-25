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
    missing = []
    if not shutil.which("ffmpeg") and not shutil.which("arecord") and not shutil.which("sox"):
        missing.append("a microphone capture tool (ffmpeg, arecord, or sox)")
    if WhisperModel is None:
        missing.append("the `faster-whisper` Python package")
        
    if missing:
        return f"Voice input is unready. Missing: {', '.join(missing)}."

    parts = []
    if shutil.which("ffmpeg"): parts.append("ffmpeg")
    elif shutil.which("arecord"): parts.append("arecord")
    elif shutil.which("sox"): parts.append("sox")
    parts.append("local Whisper STT")
        
    return "Voice input is ready locally: " + " + ".join(parts) + "."

def start_continuous_recording(output_path: Optional[str] = None):
    if output_path is None:
        output_path = str(Path(tempfile.gettempdir()) / "assistant_voice_capture.wav")
        
    if Path(output_path).exists():
        try: Path(output_path).unlink()
        except: pass

    process = None
    if shutil.which("arecord"):
        cmd = ["arecord", "-D", "default", "-f", "cd", "-t", "wav", output_path]
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif shutil.which("ffmpeg"):
        cmd = ["ffmpeg", "-y", "-f", "alsa", "-i", "default", output_path]
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif shutil.which("sox"):
        cmd = ["sox", "-d", output_path]
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
    return process, output_path

def stop_continuous_recording(process) -> Optional[str]:
    if process:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    return None

def transcribe_audio_file(audio_path: str) -> str:
    """Transcribe a saved audio file with local Whisper when available."""
    if WhisperModel is None:
        return "Speech-to-text backend is not available. Please install `faster-whisper`."
    if not audio_path or not Path(audio_path).exists() or Path(audio_path).stat().st_size < 100:
        return "No valid audio was captured."

    try:
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(audio_path, beam_size=5)
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        if text:
            return text
        return "No clear speech detected."
    except Exception as exc:
        return f"Voice transcription failed: {exc}"

def transcribe_audio_from_microphone(record_seconds: int = 5) -> str:
    """Legacy single-shot record."""
    proc, path = start_continuous_recording()
    if not proc:
        return "No capture tool found (install ffmpeg, arecord, or sox)."
    import time
    time.sleep(record_seconds)
    stop_continuous_recording(proc)
    return transcribe_audio_file(path)

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
    """Use Gemini to analyze a captured image when a valid API key is available, fallback to local OCR."""
    if not image_path or not Path(image_path).exists():
        return "No valid image file was provided for screen analysis."
        
    def _local_ocr_fallback():
        import subprocess
        import shutil
        if shutil.which("tesseract"):
            try:
                res = subprocess.run(["tesseract", image_path, "stdout"], capture_output=True, text=True, check=False)
                ocr_text = res.stdout.strip()
                if ocr_text:
                    return f"**[Local OCR Fallback - No Vision Model Available]**\n\nExtracted text from screen:\n```\n{ocr_text}\n```"
                return "[Local OCR Fallback] Failed to extract any valid text from the image."
            except Exception as e:
                return f"[Local OCR Fallback Error]: {e}"
        return "Gemini image analysis is unavailable, and local 'tesseract' is not installed for OCR."

    if genai is None or genai_types is None:
        return _local_ocr_fallback()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return _local_ocr_fallback()

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
        t = _extract_text_from_response(response)
        if t.strip():
            return t.strip()
        return "Gemini processed the image, but it returned no readable description."
    except Exception as exc:
        print(f"Gemini API failed during vision task, falling back to local OCR: {exc}")
        return _local_ocr_fallback()


def describe_current_screen(question: str = "Analyze the full desktop screen. Provide a high-level overview of open applications, desktop layout, visible menus, and any active notifications. Use Markdown headers for organization.") -> str:
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
