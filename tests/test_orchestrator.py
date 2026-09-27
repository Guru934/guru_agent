import unittest

from agent.policy import AgentOrchestrator


class AgentOrchestratorTests(unittest.TestCase):
    def test_simple_question_is_direct(self):
        plan = AgentOrchestrator().decide("What is the capital of France?")
        self.assertEqual(plan.route, "direct")
        self.assertEqual(plan.tool_calls, [])

    def test_file_work_is_delegated(self):
        plan = AgentOrchestrator().decide("Search the project for auth logic and read the login file")
        self.assertEqual(plan.route, "delegate")
        self.assertIn("search", plan.tool_calls)
        self.assertIn("read_file", plan.tool_calls)

    def test_cloud_like_request_uses_gemini(self):
        plan = AgentOrchestrator().decide("What are the latest AI trends and summarize them for me")
        self.assertEqual(plan.route, "delegate")
        self.assertEqual(plan.preferred_model, "gemini-2.5-flash")

    def test_desktop_command_uses_assistant_path(self):
        plan = AgentOrchestrator().decide("open youtube and play some music")
        self.assertEqual(plan.route, "desktop_action")


if __name__ == "__main__":
    unittest.main()
