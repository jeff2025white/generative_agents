import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


if "openai" not in sys.modules:
    openai_stub = SimpleNamespace(
        api_key=None,
        api_base=None,
        ChatCompletion=SimpleNamespace(create=lambda **kwargs: {"choices": [{"message": {"content": "stub"}}]}),
        Embedding=SimpleNamespace(create=lambda **kwargs: {"data": [{"embedding": [1.0, 0.0]}]}),
    )
    sys.modules["openai"] = openai_stub

if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda a: sum(x * x for x in a) ** 0.5
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub


from persona.prompt_template.gpt_structure import _extract_ollama_metrics


class OllamaTimingMetricTests(unittest.TestCase):
    def test_extract_ollama_metrics_from_response_dict(self):
        response = {
            "total_duration": 12_000_000_000,
            "load_duration": 300_000_000,
            "prompt_eval_duration": 1_800_000_000,
            "eval_duration": 9_900_000_000,
            "prompt_eval_count": 812,
            "eval_count": 98,
        }

        metrics = _extract_ollama_metrics(response)

        self.assertEqual(metrics["total_ms"], 12000.0)
        self.assertEqual(metrics["load_ms"], 300.0)
        self.assertEqual(metrics["prompt_eval_ms"], 1800.0)
        self.assertEqual(metrics["eval_ms"], 9900.0)
        self.assertEqual(metrics["prompt_eval_count"], 812)
        self.assertEqual(metrics["eval_count"], 98)


if __name__ == "__main__":
    unittest.main()
