import unittest
from unittest.mock import patch

from agent.fast_actions import FastAction, resolve_fast_action


class FastActionResolverTests(unittest.TestCase):
    def test_open_youtube_is_deterministic(self):
        action = resolve_fast_action("open youtube")
        self.assertEqual(action, FastAction("open_website", {"url": "https://youtube.com"}))

    def test_max_volume_is_deterministic(self):
        action = resolve_fast_action("max the volume")
        self.assertEqual(action, FastAction("set_volume", {"level_percent": 100}))

    def test_set_volume_number_is_deterministic(self):
        action = resolve_fast_action("set volume to 65%")
        self.assertEqual(action, FastAction("set_volume", {"level_percent": 65}))

    def test_normal_question_is_not_fast_action(self):
        self.assertIsNone(resolve_fast_action("what is volume normalization?"))


class FastActionRuntimeTests(unittest.TestCase):
    def test_runtime_uses_tool_executor_without_provider_for_fast_action(self):
        from agent.runtime import AgentRuntime
        from agent.executor import ExecutionResult

        runtime = AgentRuntime(model_id="gemini-3.8-live")
        fake_result = ExecutionResult("success", "System volume set to 100%")

        with patch.object(runtime.executor, "execute", return_value=fake_result) as execute,              patch("agent.runtime.create_agent_session") as create_session:
            state = runtime.run("max the volume", task_id="fast-volume-test")

        execute.assert_called_once_with(
            "set_volume",
            {"level_percent": 100},
            {"task_id": "fast-volume-test", "cancel_event": unittest.mock.ANY},
        )
        create_session.assert_not_called()
        self.assertTrue(state.completed)
        self.assertIsNone(state.error)
        self.assertEqual(state.final_answer, "System volume set to 100%")


if __name__ == "__main__":
    unittest.main()
