path = "/home/guru/guru_agent/ui_scratchpad.py"
with open(path, "r") as f:
    text = f.read()

text = text.replace('self.terminal_drawer = QWidget()', 'self.terminal_drawer = QWidget()\n        self.terminal_drawer.setMinimumHeight(40)')
with open(path, "w") as f:
    f.write(text)
