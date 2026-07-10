import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from persona.cognitive_modules.social_dialogue_log import (
    build_dialogue_id,
    clear_social_dialogue_state,
    get_social_dialogue_context,
    inherit_social_dialogue_state,
    set_social_dialogue_state,
)


def make_persona(name, step=12):
    scratch = SimpleNamespace(
        curr_time=datetime(2026, 7, 1, 14, 20, 0),
        curr_step=step,
        social_dialogue_id=None,
        social_dialogue_partner=None,
        social_dialogue_role=None,
        social_dialogue_started_step=None,
    )
    return SimpleNamespace(name=name, scratch=scratch, sim_code="sim_20260701_142000")


class SocialDialogueLogTests(unittest.TestCase):
    def test_build_dialogue_id_contains_names_and_step(self):
        initiator = make_persona("Klaus Mueller", step=157)
        target = make_persona("Maria Lopez", step=157)

        dialogue_id = build_dialogue_id(initiator, target)

        self.assertIn("Klaus_Mueller", dialogue_id)
        self.assertIn("Maria_Lopez", dialogue_id)
        self.assertIn("157", dialogue_id)

    def test_state_can_be_set_inherited_and_cleared(self):
        initiator = make_persona("Klaus Mueller", step=157)
        target = make_persona("Maria Lopez", step=160)
        dialogue_id = build_dialogue_id(initiator, target)

        set_social_dialogue_state(initiator, dialogue_id, partner_name=target.name, role="init")
        inherited_id = inherit_social_dialogue_state(target, initiator, role="target")

        self.assertEqual(inherited_id, dialogue_id)
        self.assertEqual(target.scratch.social_dialogue_id, dialogue_id)
        self.assertEqual(target.scratch.social_dialogue_partner, initiator.name)
        self.assertEqual(target.scratch.social_dialogue_role, "target")

        context = get_social_dialogue_context(target)
        self.assertEqual(context["dialogue_id"], dialogue_id)
        self.assertEqual(context["target"], initiator.name)

        clear_social_dialogue_state(target)
        self.assertIsNone(target.scratch.social_dialogue_id)
        self.assertIsNone(target.scratch.social_dialogue_partner)
        self.assertIsNone(target.scratch.social_dialogue_role)

if __name__ == "__main__":
    unittest.main()
