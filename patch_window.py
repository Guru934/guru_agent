import re

with open("/home/guru/guru_agent/ui_scratchpad.py", "r") as f:
    content = f.read()

# Replace the specific override in on_active_window_snapshot_clicked
content = content.replace(
    '        summary = describe_active_window("Describe the active application window and note the visible text, widgets, and any important content.")',
    '        summary = describe_active_window()'
)

# Replace the text formatting
content = content.replace(
    'self.add_system_message_to_feed(f"Active window description:\\n{summary}", is_error=False)',
    'self.add_system_message_to_feed(f"### 🪟 Active Window Content\\n\\n{summary}", is_error=False)'
)

content = content.replace(
    'self.add_system_message_to_feed(f"Active window description:\\n{describe_active_window()}", is_error=False)',
    'self.add_system_message_to_feed(f"### 🪟 Active Window Content\\n\\n{describe_active_window()}", is_error=False)'
)

with open("/home/guru/guru_agent/ui_scratchpad.py", "w") as f:
    f.write(content)
