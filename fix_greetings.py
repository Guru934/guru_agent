path = "/home/guru/guru_agent/cat_talker/gemini_live_agent.py"
with open(path, "r") as f:
    text = f.read()

old_greeting = """                        logger.info("====================================")
                        if text_callback:
                            text_callback("system", "Connected! Speak now...")"""

new_greeting = """                        logger.info("====================================")
                        if not getattr(self, '_has_connected_once', False):
                            if text_callback:
                                text_callback("system", "Gemini Live Connected! Hold F1 to push-to-talk.")
                            self._has_connected_once = True"""

text = text.replace(old_greeting, new_greeting)

with open(path, "w") as f:
    f.write(text)

