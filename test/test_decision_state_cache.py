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


from persona.cognitive_modules.decision_state_cache import (
    build_state_signature,
    clear_cached_decisions,
    get_cached_decision,
    put_cached_decision,
)
import persona.cognitive_modules.plan as plan_module


class DecisionStateCacheTests(unittest.TestCase):
    def tearDown(self):
        clear_cached_decisions()

    def test_state_signature_changes_when_satiety_bucket_changes(self):
        sig_a = build_state_signature(
            persona_name="Klaus Mueller",
            intent_family="restore_satiety",
            satiety=24.0,
            stamina=62.0,
            health=91.0,
            mood=55.0,
            inventory_state="empty",
            reachable_targets=["cafe counter", "refrigerator"],
            cooperative_state="none",
        )
        sig_b = build_state_signature(
            persona_name="Klaus Mueller",
            intent_family="restore_satiety",
            satiety=41.0,
            stamina=62.0,
            health=91.0,
            mood=55.0,
            inventory_state="empty",
            reachable_targets=["cafe counter", "refrigerator"],
            cooperative_state="none",
        )

        self.assertNotEqual(sig_a, sig_b)

    def test_cached_decision_roundtrip_returns_copy(self):
        signature = build_state_signature(
            persona_name="Klaus Mueller",
            intent_family="restore_stamina",
            satiety=58.0,
            stamina=24.0,
            health=91.0,
            mood=55.0,
            inventory_state="empty",
            reachable_targets=["bed", "sofa"],
            cooperative_state="none",
        )
        payload = {
            "thought": "I should rest on the sofa now.",
            "action": "Rest",
            "target": "sofa",
            "detail": "resting on the sofa",
            "duration": 20,
            "reasoning": "Stamina is low.",
        }

        put_cached_decision(signature, payload)
        cached = get_cached_decision(signature)
        cached["target"] = "bed"

        self.assertEqual(get_cached_decision(signature)["target"], "sofa")

    def test_navigation_failure_disables_semantic_signature(self):
        persona = SimpleNamespace(
            name="Isabella Rodriguez",
            scratch=SimpleNamespace(
                satiety=99.0,
                stamina=62.0,
                health=91.0,
                mood=55.0,
                inventory={"apple": 24},
                get_recent_navigation_failure=lambda max_age_steps=6: {
                    "target": "apple tree",
                    "reason": "path_not_found",
                },
            ),
        )

        signature = plan_module._build_decision_state_signature(
            persona,
            "restore_satiety",
            ["apple tree", "cafe counter"],
            "No special cooperative tasks or wait states are active nearby.",
        )

        self.assertIsNone(signature)


if __name__ == "__main__":
    unittest.main()
