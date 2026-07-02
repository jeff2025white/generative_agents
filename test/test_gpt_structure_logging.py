import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


if "openai" not in sys.modules:
    openai_stub = SimpleNamespace(
        api_key=None,
        api_base=None,
        ChatCompletion=SimpleNamespace(create=lambda **kwargs: {"choices": [{"message": {"content": "stub"}}]}),
        Embedding=SimpleNamespace(create=lambda **kwargs: {"data": [{"embedding": [0.0]}]}),
    )
    sys.modules["openai"] = openai_stub


import persona.prompt_template.gpt_structure as gpt_structure


class GPTStructureLoggingTests(unittest.TestCase):
    def setUp(self):
        self.cache_backup = dict(gpt_structure._cache)
        gpt_structure._cache.clear()

    def tearDown(self):
        gpt_structure._cache.clear()
        gpt_structure._cache.update(self.cache_backup)

    def test_chatgpt_request_logs_cache_hit(self):
        prompt = "hello"
        cache_key = gpt_structure._cache_key(prompt, "chatgpt")
        gpt_structure._cache[cache_key] = "cached-response"

        with patch.object(gpt_structure, "append_debug_log") as log_mock:
            result = gpt_structure.ChatGPT_request(prompt)

        self.assertEqual(result, "cached-response")
        log_mock.assert_called_once()
        payload = log_mock.call_args.args[1]
        self.assertEqual(payload["event"], "chatgpt_request")
        self.assertTrue(payload["cache_hit"])
        self.assertEqual(payload["duration_ms"], 0.0)

    def test_chatgpt_request_logs_uncached_duration(self):
        with patch.object(gpt_structure.openai.ChatCompletion, "create", return_value={"choices": [{"message": {"content": "fresh-response"}}]}), \
             patch.object(gpt_structure, "append_debug_log") as log_mock:
            result = gpt_structure.ChatGPT_request("uncached prompt")

        self.assertEqual(result, "fresh-response")
        payload = log_mock.call_args.args[1]
        self.assertEqual(payload["event"], "chatgpt_request")
        self.assertFalse(payload["cache_hit"])
        self.assertEqual(payload["status"], "ok")
        self.assertGreaterEqual(payload["duration_ms"], 0.0)

    def test_safe_generate_response_logs_attempts_and_summary(self):
        logs = []

        def capture(_name, payload, level="info"):
            logs.append(payload)

        responses = [
            '{"output": {"action": "Idle"}}',
            '{"output": {"action": "Gather"}}',
        ]

        with patch.object(gpt_structure, "ChatGPT_request", side_effect=responses), \
             patch.object(gpt_structure, "append_debug_log", side_effect=capture):
            result = gpt_structure.ChatGPT_safe_generate_response(
                "pick an action",
                example_output='{"action":"Gather"}',
                special_instruction="Return json",
                repeat=3,
                fail_safe_response={"action": "FailSafe"},
                func_validate=lambda resp, prompt="": isinstance(resp, dict) and resp.get("action") == "Gather",
                func_clean_up=lambda resp, prompt="": resp,
            )

        self.assertEqual(result, {"action": "Gather"})
        attempt_events = [item for item in logs if item.get("event") == "chatgpt_safe_attempt"]
        summary_events = [item for item in logs if item.get("event") == "chatgpt_safe_summary"]
        self.assertEqual(len(attempt_events), 2)
        self.assertEqual(summary_events[-1]["status"], "ok")
        self.assertEqual(summary_events[-1]["attempts_used"], 2)


if __name__ == "__main__":
    unittest.main()
