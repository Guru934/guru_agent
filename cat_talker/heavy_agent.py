import os
import subprocess
import threading
from google import genai
from google.genai import types

def log_status(message: str):
    """Write updates to the status file for the UI to poll."""
    status_file = "/home/guru/guru_agent/handoff_status.txt"
    try:
        with open(status_file, "a") as f:
            f.write(message + "\n")
    except Exception:
        pass

def write_file(filepath: str, content: str) -> str:
    """Writes code or text to a file on your system."""
    log_status(f"[Heavy Agent] -> Writing to file: {filepath}")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote file: {filepath}"
    except Exception as e:
        return f"Error writing file: {e}"

def read_file(filepath: str) -> str:
    """Reads the content of a file on your system."""
    log_status(f"[Heavy Agent] -> Reading file: {filepath}")
    if not os.path.exists(filepath):
        return f"Error: File not found: {filepath}"
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"

def execute_shell(command: str) -> str:
    """Executes a bash/terminal command on your PC."""
    log_status(f"[Heavy Agent] -> Executing: {command}")
    try:
        res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
        output = res.stdout.strip()
        if res.stderr.strip():
            output += "\n[STDERR]\n" + res.stderr.strip()
        out_str = output or "Command executed successfully with no output."
        log_status(f"[Heavy Agent] -> Command Output ({len(out_str)} chars)")
        return out_str
    except Exception as e:
        return f"Execution error: {e}"

def run_heavy_agent_worker(task_description: str):
    log_status(f"[STATUS] Working")
    log_status(f"[Heavy Agent] Starting task: {task_description}")

    try:
        client = genai.Client()
        heavy_tools = [write_file, execute_shell, read_file]

        system_instruction = (
            "You are an autonomous execution agent on CachyOS Linux. "
            "You must write real scripts, read files, "
            "and run tests using execute_shell to fulfill the user's task. "
            "Complete the task directly."
        )

        import os
        selected_mod = os.environ.get("HEAVY_AGENT_MODEL", "gemini-3.1-flash-lite")
        models_to_try = [selected_mod, "gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash"]
        # deduplicate order
        models_to_try = list(dict.fromkeys(models_to_try))
        
        response = None
        for mod in models_to_try:
            try:
                log_status(f"[Heavy Agent] Prompting model: {mod}...")
                chat = client.chats.create(
                    model=mod,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=heavy_tools,
                        temperature=0.0
                    )
                )
                response = chat.send_message(task_description)
                log_status(f"[Heavy Agent] Final output: {response.text}")
                break
            except Exception as e:
                err_str = str(e)
                log_status(f"[Heavy Agent] Model {mod} failed: {err_str}")
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    log_status(f"[Heavy Agent] Quota exhausted on {mod}. Auto-switching to next model...")
                    continue
                else:
                    raise e
        
        if not response:
            log_status(f"[Heavy Agent] All models failed due to quota/errors.")


    except Exception as e:
        log_status(f"[Heavy Agent] Error during execution: {e}")

    log_status(f"[STATUS] Idle")
    log_status(f"[DONE]")

def execute_task_async(task: str):
    t = threading.Thread(target=run_heavy_agent_worker, args=(task,))
    t.daemon = True
    t.start()