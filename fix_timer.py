import re
with open("ui/main_window.py", "r") as f:
    content = f.read()

# Strip any timer declarations related to poll_heavy_agent_logs
content = re.sub(r'\s*self\.heavy_agent_log_timer.*?\n(?:[ \t]+.*?\n)*?.*?poll_heavy_agent_logs.*?\n', '\n', content, flags=re.DOTALL)
content = re.sub(r'self\.heavy_agent_log_timer = QTimer\(self\)\s+self\.heavy_agent_log_timer\.timeout\.connect\(self\.poll_heavy_agent_logs\)\s+self\.heavy_agent_log_timer\.start\(500\)', '', content)

with open("ui/main_window.py", "w") as f:
    f.write(content)
