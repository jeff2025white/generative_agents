import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


import persona.prompt_template.run_gpt_prompt as prompt_module


class EventTripleRequestConfigTests(unittest.TestCase):
    def test_event_triple_forwards_explicit_request_config(self):
        persona = SimpleNamespace(name="Maria Lopez")
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=["does", "cleanup"] ) as mocked:
            result, _ = prompt_module.run_gpt_prompt_event_triple(
                "cleaning the house",
                persona,
                request_config=config,
            )

        self.assertEqual(result, ("Maria Lopez", "does", "cleanup"))
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_event_triple_uses_task_route_when_request_config_missing(self):
        persona = SimpleNamespace(name="Klaus Mueller")
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=["is", "walking"] ) as mocked:
            result, _ = prompt_module.run_gpt_prompt_event_triple(
                "walking home",
                persona,
            )

        self.assertEqual(result, ("Klaus Mueller", "is", "walking"))
        mocked_route.assert_called_once_with("event_triple")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)


if __name__ == "__main__":
    unittest.main()
