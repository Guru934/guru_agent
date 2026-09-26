path = "/home/guru/guru_agent/cat_talker/gemini_live_agent.py"
with open(path, "r") as f:
    text = f.read()

# Remove the PTT blocking block
text = text.replace('''                            if not getattr(self, 'is_recording', False):
                                # Discard audio if PTT is not held
                                continue''', '')

with open(path, "w") as f:
    f.write(text)

