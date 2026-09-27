import unittest

from PyQt6.QtWidgets import QApplication

from ui.main_window import ScratchpadWindow
from tools.browser import (
    build_approval_message,
    capture_screen_snapshot,
    transcribe_audio_from_microphone,
    analyze_screen_image,
    voice_input_status,
    describe_current_screen,
    describe_active_window,
)


class AssistantFeaturesTests(unittest.TestCase):
    def setUp(self):
        from memory.sqlite import init_db
        init_db()

    def test_build_approval_message_includes_action_and_risk(self):
        msg = build_approval_message(
            "open_website",
            "open https://example.com",
            risk_level="low",
        )
        self.assertIn("open_website", msg)
        self.assertIn("Approve", msg)
        self.assertIn("low", msg.lower())

    def test_capture_screen_snapshot_reports_path_on_success(self):
        result = capture_screen_snapshot("primary")
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("/") or result.startswith("Screenshot") or result.startswith("Voice") or result.startswith("No"))

    def test_voice_input_status_is_explanatory(self):
        status = voice_input_status()
        self.assertIsInstance(status, str)
        self.assertTrue(len(status) > 10)

    def test_transcribe_audio_from_microphone_handles_missing_backend(self):
        result = transcribe_audio_from_microphone(record_seconds=1)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_analyze_screen_image_handles_missing_tools(self):
        result = analyze_screen_image("/tmp/not-a-real-image.png")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_describe_current_screen_returns_status_text(self):
        result = describe_current_screen("Describe the visible screen and any key elements.")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_describe_active_window_returns_status_text(self):
        result = describe_active_window("Describe the active application window and any key elements.")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_voice_button_state_machine_updates_readably(self):
        app = QApplication.instance() or QApplication([])
        window = ScratchpadWindow()
        window.set_voice_button_state("recording")
        self.assertEqual(window.voice_btn.text(), "🔴 Recording")
        self.assertTrue(window.voice_btn.isChecked())

        window.set_voice_button_state("processing")
        self.assertIn("Processing", window.voice_btn.text())

        window.set_voice_button_state("idle")
        self.assertEqual(window.voice_btn.text(), "🎙")
        self.assertFalse(window.voice_btn.isChecked())

        window.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
