import os
import subprocess

def execute_bash_command(command: str, cwd: str = None) -> str:
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd or os.getcwd()
    )
    output = result.stdout.strip() or result.stderr.strip() or "Command completed without output."
    return output

def ripgrep_search_impl(query: str, cwd: str = None) -> str:
    try:
        result = subprocess.run(
            ["rg", "-n", query, "."],
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd or os.getcwd(),
        )
        if result.stdout.strip():
            return result.stdout.strip()
        return "No matches found."
    except FileNotFoundError:
        return "rg is not installed. Install ripgrep if you want search support."
