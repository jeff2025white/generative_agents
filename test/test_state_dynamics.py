import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from persona.cognitive_modules.state_dynamics import (
    apply_step_state_dynamics,
    derive_step_state_deltas,
)


def make_persona(*, satiety=80.0, stamina=80.0, health=90.0, mood=70.0, act_description="reading quietly", chatting_with=None, planned_path=None, active_execution_state=None):
    scratch = SimpleNamespace(
        satiety=satiety,
        stamina=stamina,
        health=health,
        mood=mood,
        act_description=act_description,
        chatting_with=chatting_with,
        planned_path=planned_path,
        last_social_time=None,
        active_execution_state=active_execution_state,
    )
    return SimpleNamespace(name="Klaus Mueller", scratch=scratch)


class StateDynamicsTests(unittest.TestCase):
    def test_sleeping_uses_same_shared_step_rules(self):
        persona = make_persona(
            satiety=85.0,
            stamina=85.0,
            health=90.0,
            mood=70.0,
            act_description="sleeping in bed",
        )

        deltas = derive_step_state_deltas(persona)

        self.assertEqual(deltas["satiety"], -0.04)
        self.assertEqual(deltas["stamina"], 0.15)
        self.assertEqual(deltas["mood"], -0.02)
        self.assertEqual(deltas["health"], 0.01)

    def test_moving_persona_spends_more_stamina(self):
        persona = make_persona(
            satiety=60.0,
            stamina=50.0,
            health=90.0,
            mood=55.0,
            act_description="walking to the cafe",
            planned_path=[(1, 1), (2, 1)],
        )

        deltas = derive_step_state_deltas(persona)

        self.assertEqual(deltas["satiety"], -0.08)
        self.assertEqual(deltas["stamina"], -0.07)
        self.assertEqual(deltas["mood"], -0.06)

    def test_social_step_updates_last_social_time(self):
        persona = make_persona(
            satiety=70.0,
            stamina=72.0,
            health=88.0,
            mood=40.0,
            act_description="chatting at the square",
            chatting_with="Maria Lopez",
        )
        curr_time = datetime(2026, 7, 8, 15, 0, 0)

        apply_step_state_dynamics(persona, curr_time=curr_time)

        self.assertEqual(persona.scratch.last_social_time, curr_time)
        self.assertGreater(persona.scratch.mood, 40.0)

    def test_pathing_to_rest_does_not_grant_rest_recovery_early(self):
        persona = make_persona(
            satiety=70.0,
            stamina=35.0,
            health=88.0,
            mood=45.0,
            act_description="sleeping in bed to recharge stamina",
            planned_path=[(1, 1), (2, 1), (3, 1)],
            active_execution_state={"phase": "pathing"},
        )

        deltas = derive_step_state_deltas(persona)

        self.assertEqual(deltas["satiety"], -0.08)
        self.assertEqual(deltas["stamina"], -0.07)
        self.assertLess(deltas["mood"], 0.0)


if __name__ == "__main__":
    unittest.main()
