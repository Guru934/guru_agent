path = "/home/guru/guru_agent/ui_scratchpad.py"
with open(path, "r") as f:
    text = f.read()

poll_search = """                # Append to terminal area
                current_text = self.terminal_text_area.toPlainText()
                if "[Heavy Agent]" in new_logs and not self.terminal_text_area.isVisible():
                    self.toggle_terminal_drawer() # pop it open!"""

poll_replace = """                # Append to terminal area
                current_text = self.terminal_text_area.toPlainText()
                if "[Heavy Agent]" in new_logs and not self.terminal_text_area.isVisible():
                    self.toggle_terminal_drawer() # pop it open!
                    
                if "429 RESOURCE_EXHAUSTED" in new_logs or "Error during execution:" in new_logs:
                    self.add_system_message_to_feed("Heavy Agent failed due to API Quota / Error. Check terminal drawer.", is_error=True)
"""
text = text.replace(poll_search, poll_replace)
with open(path, "w") as f:
    f.write(text)
