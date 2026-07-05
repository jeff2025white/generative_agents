import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


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


from persona.prompt_template.gpt_structure import _cache_scope, get_cache_sim_scope, set_cache_sim_scope


class LlmCacheScopeTests(unittest.TestCase):
    def tearDown(self):
        set_cache_sim_scope(None)

    def test_cache_scope_includes_current_sim_code(self):
        set_cache_sim_scope("sim_20260705_114436")

        scope = _cache_scope(
            "chatgpt",
            {
                "api_key": "dummy",
                "api_base": "https://api.example/v1",
                "model": "glm-4-flash",
            },
        )

        self.assertIn('"sim_code": "sim_20260705_114436"', scope)
        self.assertEqual(get_cache_sim_scope(), "sim_20260705_114436")

    def test_cache_scope_changes_between_simulations(self):
        config = {
            "api_key": "dummy",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }
        set_cache_sim_scope("sim_a")
        scope_a = _cache_scope("chatgpt", config)

        set_cache_sim_scope("sim_b")
        scope_b = _cache_scope("chatgpt", config)

        self.assertNotEqual(scope_a, scope_b)


if __name__ == "__main__":
    unittest.main()
