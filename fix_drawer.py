path = "/home/guru/guru_agent/ui_scratchpad.py"
with open(path, "r") as f:
    text = f.read()

# Make the auto-expansion happen in poll_heavy_agent_logs
poll_search = """                # Append to terminal area
                current_text = self.terminal_text_area.toPlainText()"""

poll_replace = """                # Append to terminal area
                current_text = self.terminal_text_area.toPlainText()
                if "[Heavy Agent]" in new_logs and not self.terminal_text_area.isVisible():
                    self.toggle_terminal_drawer() # pop it open!
"""
text = text.replace(poll_search, poll_replace)

# Fix possible issue with sizes
text = text.replace("self.chat_splitter.setSizes([800, 30])", "self.chat_splitter.setSizes([800, 40])")

with open(path, "w") as f:
    f.write(text)
