import os
import unittest
from unittest.mock import MagicMock, patch

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

    def test_search_and_play_youtube_is_deterministic(self):
        action = resolve_fast_action("Search and play 'Kalyani song' on YouTube")
        self.assertEqual(
            action,
            FastAction("search_and_play_youtube", {"query": "kalyani song"}),
        )

    def test_normal_question_is_not_fast_action(self):
        self.assertIsNone(resolve_fast_action("what is volume normalization?"))

    def test_live_model_is_mapped_to_heavy_execution_model(self):
        from agent.model_provider import AgentResponse
        from agent.runtime import AgentRuntime

        old_model = os.environ.get("HEAVY_AGENT_MODEL")
        os.environ["HEAVY_AGENT_MODEL"] = "qwen2.5-coder:1.5b"
        fake_session = MagicMock()
        fake_session.send_message.return_value = AgentResponse("done", [])
        try:
            runtime = AgentRuntime(model_id="gemini-3.8-live")
            with patch("agent.runtime.create_agent_session", return_value=fake_session) as create:
                state = runtime.run(
                    "write a Python script that prints hello guru",
                    task_id="live-model-routing-test",
                )
            create.assert_called_once()
            self.assertEqual(create.call_args.args[0], "qwen2.5-coder:1.5b")
            self.assertTrue(state.completed)
            self.assertIsNone(state.error)
        finally:
            if old_model is None:
                os.environ.pop("HEAVY_AGENT_MODEL", None)
            else:
                os.environ["HEAVY_AGENT_MODEL"] = old_model


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

    def test_gemini_session_keeps_client_alive_until_close(self):
        from agent.model_provider import GeminiAgentSession

        fake_client = MagicMock()
        with patch("agent.model_provider.genai.Client", return_value=fake_client):
            session = GeminiAgentSession(
                "gemini-3.1-flash-lite",
                "test",
                [],
                [],
            )

        self.assertIs(session.client, fake_client)
        self.assertIs(session.chat, fake_client.chats.create.return_value)
        session.close()
        fake_client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
