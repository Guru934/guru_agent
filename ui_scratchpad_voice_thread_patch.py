from PyQt6.QtCore import QThread, pyqtSignal

class VoiceCaptureWorker(QThread):
    finished_signal = pyqtSignal(str)

    def __init__(self, record_seconds=4):
        super().__init__()
        self.record_seconds = record_seconds

    def run(self):
        from cat_talker.assistant_features import transcribe_audio_from_microphone
        transcript = transcribe_audio_from_microphone(record_seconds=self.record_seconds)
        self.finished_signal.emit(transcript)
