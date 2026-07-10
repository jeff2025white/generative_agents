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
        ChatCompletion=SimpleNamespace(
            create=lambda **kwargs: {"choices": [{"message": {"content": "stub"}}]}
        ),
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


import persona.cognitive_modules.skill_packs.rest_skill as rest_skill_module
from persona.cognitive_modules.food_sources import normalize_food_source_target
from persona.cognitive_modules.skill_packs.consume_skill import ConsumeSkillPack
from persona.cognitive_modules.skill_packs.rest_skill import RestSkillPack


class KlausIsabellaEatingFixTests(unittest.TestCase):
    """Regression tests for cafe food targeting and sticky rest actions."""

    def test_normalize_food_source_target_maps_cafe_seating_aliases(self):
        """Cafe seating and meal aliases should resolve to an executable counter target."""
        self.assertEqual(normalize_food_source_target("cafe customer seating"), "cafe counter")
        self.assertEqual(
            normalize_food_source_target("Hobbs Cafe cafe customer seating"),
            "cafe counter",
        )
        self.assertEqual(normalize_food_source_target("cooked meal"), "cafe counter")
        self.assertEqual(normalize_food_source_target("café"), "cafe counter")

    def test_consume_can_execute_accepts_cafe_customer_seating_address(self):
        """Consume should accept cafe seating addresses via normalized food-source semantics."""
        maze = SimpleNamespace(
            access_tile=lambda tile: {"game_object": ""},
        )
        persona = SimpleNamespace(
            name="Klaus Mueller",
            scratch=SimpleNamespace(
                curr_tile=[79, 21],
                inventory={},
                act_address="the Ville:Hobbs Cafe:cafe:cafe customer seating",
                recent_completed_action_signature=None,
                recent_completed_action_step=None,
                curr_step=21,
            ),
        )

        self.assertTrue(ConsumeSkillPack().can_execute(persona, "cooked meal", maze))

    def test_consume_on_arrive_logs_progress_score_breakdown(self):
        logged_payloads = []
        completed_calls = []
        scratch = SimpleNamespace(
            satiety=20.0,
            health=80.0,
            mood=40.0,
            stamina=50.0,
            curr_step=8,
            curr_time=None,
            curr_tile=[79, 21],
            inventory={"apple": 1},
            act_command={"skill_id": "consume", "target": "apple"},
            act_event=("Klaus Mueller", "consume", "apple"),
            act_description="eating an apple from inventory",
            act_address="inventory",
            planned_path=[[79, 21]],
            act_path_set=True,
            skills={"cooking": {"xp": 0, "level": 1}},
            mark_action_completed=lambda **kwargs: completed_calls.append(kwargs),
        )
        persona = SimpleNamespace(
            name="Klaus Mueller",
            scratch=scratch,
            a_mem=None,
        )
        maze = SimpleNamespace(access_tile=lambda tile: {"game_object": ""})

        with patch("persona.cognitive_modules.skill_packs.consume_skill.append_debug_log") as mock_log, patch(
            "persona.cognitive_modules.skill_packs.consume_skill.record_stat_change_experience"
        ):
            mock_log.side_effect = lambda _name, payload: logged_payloads.append(payload)
            ConsumeSkillPack().on_arrive(persona, "apple", maze, {})

        end_logs = [item for item in logged_payloads if item.get("event") == "on_arrive_end"]
        self.assertEqual(len(end_logs), 1)
        self.assertIn("progress_score", end_logs[0])
        self.assertIn("progress_score_breakdown", end_logs[0])
        self.assertEqual(
            end_logs[0]["progress_score"],
            end_logs[0]["progress_score_breakdown"]["score"],
        )
        self.assertGreater(end_logs[0]["progress_score_breakdown"]["attribute_score"], 0.0)
        self.assertEqual(len(completed_calls), 1)

    def test_rest_on_arrive_marks_action_completed_and_releases_plan(self):
        """Rest completion should release the stuck action state so replanning can resume."""
        completed_calls = []
        scratch = SimpleNamespace(
            stamina=60.0,
            satiety=30.7,
            health=100.0,
            mood=75.0,
            curr_step=115,
            curr_time=None,
            act_command={"skill_id": "rest", "target": "bed"},
            act_event=("Isabella Rodriguez", "rest", "bed"),
            act_description="lying down on the bed to rest",
            act_address="the Ville:Isabella Rodriguez's apartment:main room:bed",
            planned_path=[[73, 14]],
            act_path_set=True,
            skills={},
            mark_action_completed=lambda **kwargs: completed_calls.append(kwargs),
        )
        persona = SimpleNamespace(
            name="Isabella Rodriguez",
            scratch=scratch,
            a_mem=None,
        )

        with patch.object(rest_skill_module, "append_debug_log"), patch.object(
            rest_skill_module, "record_stat_change_experience"
        ):
            RestSkillPack().on_arrive(persona, "bed", None, {})

        self.assertEqual(persona.scratch.stamina, 100.0)
        self.assertEqual(persona.scratch.planned_path, [])
        self.assertFalse(persona.scratch.act_path_set)
        self.assertEqual(len(completed_calls), 1)
        self.assertEqual(
            completed_calls[0]["action_command"],
            {"skill_id": "rest", "target": "bed"},
        )


if __name__ == "__main__":
    unittest.main()
