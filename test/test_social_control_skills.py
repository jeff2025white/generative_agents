import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).parent.parent
BACKEND = ROOT / "reverie" / "backend_server"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.chdir(str(BACKEND))

from persona.cognitive_modules.motive_selector import build_default_motive_attributes
from persona.cognitive_modules.skill_packs import SKILL_REGISTRY


def _make_persona(name, curr_tile=(0, 0)):
    scratch = SimpleNamespace(
        inventory={},
        curr_tile=curr_tile,
        act_command={"skill_id": "coordinate", "target": "none", "detail": ""},
        act_event=(name, "coordinate", "none"),
        act_description="coordinating with someone nearby",
        act_address=f"<persona> {name}",
        mark_action_completed=Mock(),
        clear_current_action=Mock(),
        stamina=50.0,
        mood=50.0,
        health=80.0,
        satiety=60.0,
        motive_attributes=build_default_motive_attributes(
            overrides={
                "safety": {"current_value": 40.0},
                "belonging": {"current_value": 40.0},
                "autonomy": {"current_value": 40.0},
                "competence": {"current_value": 40.0},
            }
        ),
    )
    a_mem = SimpleNamespace(
        update_relationship=Mock(),
        get_relationship=Mock(return_value=None),
    )
    return SimpleNamespace(name=name, scratch=scratch, a_mem=a_mem)


class SocialControlSkillTests(unittest.TestCase):
    def test_coordinate_skill_recovers_belonging_and_competence(self):
        actor = _make_persona("Maria Lopez")
        partner = _make_persona("Klaus Mueller")
        personas = {actor.name: actor, partner.name: partner}
        pack = SKILL_REGISTRY["coordinate"]

        with patch("persona.cognitive_modules.skill_packs.coordinate_skill.record_stat_change_experience") as mock_exp:
            pack.on_arrive(actor, partner.name, None, personas)

        self.assertEqual(actor.scratch.motive_attributes["belonging"]["current_value"], 46.0)
        self.assertEqual(actor.scratch.motive_attributes["competence"]["current_value"], 44.0)
        actor.scratch.mark_action_completed.assert_called_once()
        mock_exp.assert_called_once()

    def test_pressure_skill_boosts_autonomy_but_costs_mood_and_belonging(self):
        actor = _make_persona("Maria Lopez")
        target = _make_persona("Isabella Rodriguez")
        personas = {actor.name: actor, target.name: target}
        pack = SKILL_REGISTRY["pressure"]

        with patch("persona.cognitive_modules.skill_packs.pressure_skill.record_stat_change_experience") as mock_exp:
            pack.on_arrive(actor, target.name, None, personas)

        self.assertEqual(actor.scratch.motive_attributes["autonomy"]["current_value"], 45.0)
        self.assertEqual(actor.scratch.motive_attributes["belonging"]["current_value"], 34.0)
        self.assertEqual(actor.scratch.mood, 47.0)
        actor.scratch.mark_action_completed.assert_called_once()
        mock_exp.assert_called_once()

    def test_avoid_skill_recovers_safety_and_stamina(self):
        actor = _make_persona("Maria Lopez")
        target = _make_persona("Isabella Rodriguez")
        personas = {actor.name: actor, target.name: target}
        pack = SKILL_REGISTRY["avoid"]

        with patch("persona.cognitive_modules.skill_packs.avoid_skill.record_stat_change_experience") as mock_exp:
            pack.on_arrive(actor, target.name, None, personas)

        self.assertEqual(actor.scratch.motive_attributes["safety"]["current_value"], 46.0)
        self.assertEqual(actor.scratch.stamina, 52.0)
        actor.scratch.mark_action_completed.assert_called_once()
        mock_exp.assert_called_once()


if __name__ == "__main__":
    unittest.main()
