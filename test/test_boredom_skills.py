import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
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

if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda a: sum(x * x for x in a) ** 0.5
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub


from persona.cognitive_modules.action_command_utils import infer_intent_family, normalize_skill_id
from persona.cognitive_modules.plan import _maybe_promote_boredom_recovery
from persona.cognitive_modules.skill_packs import SKILL_REGISTRY


class BoredomSkillTests(unittest.TestCase):
    def test_daydream_skill_normalizes_from_idle_detail(self):
        skill_id = normalize_skill_id(
            "idle",
            target="bench",
            detail="daydreaming quietly at the bench and people-watching for a while",
        )
        self.assertEqual(skill_id, "daydream")
        self.assertEqual(infer_intent_family(skill_id=skill_id, target="bench"), "leisure")

    def test_wander_skill_normalizes_from_recreate_park_detail(self):
        skill_id = normalize_skill_id(
            "recreate",
            target="park garden",
            detail="strolling through the park garden to unwind and clear my head",
        )
        self.assertEqual(skill_id, "wander")
        self.assertEqual(infer_intent_family(skill_id=skill_id, target="park garden"), "leisure")

    def test_skill_registry_contains_boredom_skills(self):
        self.assertIn("daydream", SKILL_REGISTRY)
        self.assertIn("wander", SKILL_REGISTRY)

    def test_low_mood_idle_gets_promoted_to_wander(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                mood=45.0,
                satiety=82.0,
                stamina=76.0,
                health=91.0,
                curr_tile=(10, 10),
            ),
        )
        maze = SimpleNamespace(
            get_tile_path=lambda tile, level: {"game_object": None, "arena": "sidewalk"}.get(level),
        )

        with patch(
            "persona.cognitive_modules.plan.resolve_action_target_address",
            return_value=("the Ville:Johnson Park:park", {"kind": "known_arena", "matched": "park"}),
        ):
            action, target, detail, reasoning = _maybe_promote_boredom_recovery(
                persona,
                maze,
                "Idle",
                "none",
                "idling",
                "Mood is low.",
            )

        self.assertEqual(action, "Recreate")
        self.assertEqual(target, "park garden")
        self.assertIn("strolling", detail)
        self.assertIn("low mood leisure fallback", reasoning)


if __name__ == "__main__":
    unittest.main()
