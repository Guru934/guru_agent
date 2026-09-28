import unittest

from agent.assistant_events import AssistantEvent
from providers.gemini_live import GeminiDesktopAgent


class GeminiLiveEventForwardingTests(unittest.TestCase):
    def test_forwards_only_task_milestones(self):
        for event_type in (
            "task_started",
            "approval_required",
            "task_blocked",
            "task_completed",
            "task_failed",
        ):
            with self.subTest(event_type=event_type):
                event = AssistantEvent(type=event_type, task_id="task", summary="milestone")
                self.assertTrue(GeminiDesktopAgent._is_task_milestone_event(event))

    def test_does_not_forward_tool_progress(self):
        event = AssistantEvent(type="tool_progress", task_id="task", summary="tool ran")
        self.assertFalse(GeminiDesktopAgent._is_task_milestone_event(event))


if __name__ == "__main__":
    unittest.main()
