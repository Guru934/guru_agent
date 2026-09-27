import sys
import shutil

def run_diagnostics():
    print("Running startup diagnostics...")
    
    # Check Python version
    if sys.version_info < (3, 9):
        print("WARNING: Python 3.9+ is recommended.")
        
    # Check screen capture dependencies based on OS
    if not shutil.which("grim") and not shutil.which("scrot"):
        print("WARNING: Screen capture tools 'grim' or 'scrot' not found. Vision might fail.")
        
    # Check API Key
    import os
    from config import DB_PATH
    import sqlite3
    
    try:
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT value FROM preferences WHERE key = 'api_key'")
            row = cur.fetchone()
            conn.close()
            has_api_key = True if row and row[0] else False
        else:
            has_api_key = False
    except Exception:
        has_api_key = False
        
    if not has_api_key and not os.environ.get("GEMINI_API_KEY"):
        print("WARNING: No Gemini API Key configured in database or GEMINI_API_KEY environment variable.")
        
    print("Diagnostics complete.\n")

if __name__ == "__main__":
    run_diagnostics()
