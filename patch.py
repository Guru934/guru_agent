import sys
with open("/home/guru/guru_agent/ui_scratchpad.py", "r") as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if "class ScratchpadWindow(QMainWindow):" in line:
        worker_code = """
class VoiceCaptureWorker(QThread):
    finished_signal = pyqtSignal(str)

    def __init__(self, record_seconds=4):
        super().__init__()
        self.record_seconds = record_seconds

    def run(self):
        from cat_talker.assistant_features import transcribe_audio_from_microphone
        transcript = transcribe_audio_from_microphone(record_seconds=self.record_seconds)
        self.finished_signal.emit(transcript)

"""
        new_lines.append(worker_code)
    new_lines.append(line)

with open("/home/guru/guru_agent/ui_scratchpad.py", "w") as f:
    f.writelines(new_lines)
