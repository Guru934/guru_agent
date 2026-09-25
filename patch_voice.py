import re

with open("/home/guru/guru_agent/ui_scratchpad.py", "r") as f:
    content = f.read()

replacement = """    def start_voice_capture(self):
        if self.voice_in_progress:
            return
        self.voice_in_progress = True
        self.voice_btn.setChecked(True)
        self.voice_btn.setText("🔴 Listen...")
        self.voice_btn.setToolTip("Recording audio...")
        self.voice_btn.setStyleSheet("QPushButton { background: #ff5555; color: white; border: none; border-radius: 10px; padding-left: 5px; padding-right: 5px; }")
        self.input_box.setDisabled(True)
        self.input_box.setPlaceholderText("Listening...")

        self.voice_worker = VoiceCaptureWorker(record_seconds=4)
        self.voice_worker.finished_signal.connect(self.finish_voice_capture)
        self.voice_worker.start()

    def finish_voice_capture(self, transcript: str):
        if not self.voice_in_progress:
            return

        self.voice_in_progress = False
        self.voice_btn.setChecked(False)
        self.voice_btn.setText("🎙")
        self.voice_btn.setToolTip("Hold to talk")
        self.voice_btn.setStyleSheet("QPushButton { background: #3b4261; color: white; border: none; border-radius: 10px; }")
        
        self.input_box.setDisabled(False)
        self.input_box.setPlaceholderText("Type a message or use commands like 'open browser'...")

        if transcript.strip():
            self.input_box.setPlainText(transcript.strip())
            self.add_system_message_to_feed(f"Voice capture result: {transcript}", is_error=False)

    def on_voice_status_clicked(self):
        self.start_voice_capture()
"""

# Regex replacing those 3 functions
pattern = re.compile(
    r'    def start_voice_capture\(self\):.*?(?=(    def on_screen_snapshot_clicked|    def send_message))',
    re.DOTALL
)

new_content = pattern.sub(replacement, content)
with open("/home/guru/guru_agent/ui_scratchpad.py", "w") as f:
    f.write(new_content)
