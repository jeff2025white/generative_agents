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


import persona.cognitive_modules.intent_memory as intent_memory
from persona.memory_structures.scratch import Scratch
from persona.cognitive_modules.skill_packs.gather_skill import GatherSkillPack


class RestoreSatietyLoopGuardTests(unittest.TestCase):
    """Regression tests for redundant restore-satiety loops around refrigerators."""

    def test_completed_action_is_not_reported_as_active_signature(self):
        """A completed decision must not be exposed as the currently active action."""
        scratch = Scratch(str(ROOT / "test" / "__missing_scratch__.json"))
        scratch.last_decision_signature = {
            "intent_family": "restore_satiety",
            "skill_id": "gather",
            "target": "refrigerator",
        }
        scratch.act_command = None
        scratch.act_event = None
        scratch.act_address = None
        scratch.planned_path = []

        self.assertIsNone(scratch.get_active_decision_signature())

    def test_recent_gather_does_not_force_food_memory_when_satiety_is_healthy(self):
        """Healthy satiety should suppress stale restore-satiety memory focus."""
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                satiety=78.3,
                stamina=98.8,
                health=100.0,
                mood=99.7,
                inventory={"apple": 1},
                recent_completed_action_signature={
                    "intent_family": "restore_satiety",
                    "skill_id": "gather",
                    "target": "refrigerator",
                },
            )
        )

        result = intent_memory.infer_memory_focus(persona, action_signature={})
        self.assertIsNone(result)

    def test_recent_healthy_refrigerator_gather_is_blocked(self):
        """A persona with healthy satiety and food on hand should not regather immediately."""
        maze = SimpleNamespace(
            get_tile_path=lambda tile, key: "refrigerator" if key == "game_object" else None
        )
        scratch = SimpleNamespace(
            curr_tile=[122, 45],
            satiety=78.3,
            inventory={"apple": 1},
            curr_step=20,
            recent_completed_action_step=19,
            recent_completed_action_signature={
                "intent_family": "restore_satiety",
                "skill_id": "gather",
                "target": "refrigerator",
            },
            is_recent_duplicate_action=lambda signature, within_steps=2: False,
            act_address="the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
        )
        persona = SimpleNamespace(
            name="Maria Lopez",
            scratch=scratch,
            s_mem=SimpleNamespace(find_nearest_object=lambda target: None),
        )

        result = GatherSkillPack().can_execute(persona, "refrigerator", maze)
        self.assertFalse(result)
