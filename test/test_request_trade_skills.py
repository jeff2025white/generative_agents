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

from persona.cognitive_modules.skill_packs import SKILL_REGISTRY


def _make_persona(name, inventory, curr_tile=(0, 0)):
    scratch = SimpleNamespace(
        inventory=dict(inventory),
        curr_tile=curr_tile,
        act_command={"skill_id": "request", "target": "none", "detail": ""},
        act_event=(name, "request", "none"),
        act_description="asking for food",
        act_address=f"<persona> {name}",
        mark_action_completed=Mock(),
        clear_current_action=Mock(),
        stamina=60.0,
        mood=45.0,
        health=80.0,
        satiety=25.0,
        motive_attributes={},
    )
    a_mem = SimpleNamespace(
        update_relationship=Mock(),
        get_relationship=Mock(return_value=None),
    )
    return SimpleNamespace(name=name, scratch=scratch, a_mem=a_mem)


class RequestTradeSkillTests(unittest.TestCase):
    def test_request_skill_is_registered_and_transfers_item(self):
        requester = _make_persona("Maria Lopez", {})
        helper = _make_persona("Klaus Mueller", {"apple": 2})
        personas = {requester.name: requester, helper.name: helper}
        request_pack = SKILL_REGISTRY["request"]

        with patch("persona.cognitive_modules.skill_packs.request_skill.record_stat_change_experience") as mock_exp:
            request_pack.on_arrive(requester, helper.name, None, personas)

        self.assertEqual(requester.scratch.inventory["apple"], 1)
        self.assertEqual(helper.scratch.inventory["apple"], 1)
        requester.scratch.mark_action_completed.assert_called_once()
        outcome_effects = requester.scratch.mark_action_completed.call_args.kwargs["outcome_effects"]
        self.assertEqual(outcome_effects["inventory_delta"], {"apple": 1})
        self.assertGreater(outcome_effects["progress_score"], 0.0)
        self.assertEqual(mock_exp.call_count, 2)

    def test_trade_skill_is_registered_and_accepts_future_favor_when_inventory_empty(self):
        trader = _make_persona("Maria Lopez", {})
        partner = _make_persona("Isabella Rodriguez", {"snack": 1})
        personas = {trader.name: trader, partner.name: partner}
        trade_pack = SKILL_REGISTRY["trade"]

        with patch("persona.cognitive_modules.skill_packs.trade_skill.record_stat_change_experience") as mock_exp:
            trade_pack.on_arrive(trader, partner.name, None, personas)

        self.assertEqual(trader.scratch.inventory["snack"], 1)
        self.assertEqual(partner.scratch.inventory["snack"], 0)
        trader.scratch.mark_action_completed.assert_called_once()
        outcome_effects = trader.scratch.mark_action_completed.call_args.kwargs["outcome_effects"]
        self.assertEqual(outcome_effects["inventory_delta"], {"snack": 1})
        self.assertGreater(outcome_effects["progress_score"], 0.0)
        self.assertEqual(mock_exp.call_count, 2)


if __name__ == "__main__":
    unittest.main()
