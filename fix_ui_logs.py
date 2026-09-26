path = "/home/guru/guru_agent/ui_scratchpad.py"
with open(path, "r") as f:
    text = f.read()

# Remove the noisy prints
text = text.replace('self.state_signal.connect(lambda s: print(f"Visualizer State: {s}"))', '')
text = text.replace('self.glow_signal.connect(lambda s: print(f"Visualizer Glow: {s}"))', '')

with open(path, "w") as f:
    f.write(text)

