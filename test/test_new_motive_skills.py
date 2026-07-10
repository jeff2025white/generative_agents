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
from persona.cognitive_modules.motive_selector import build_default_motive_attributes
from persona.cognitive_modules.plan import decide_demand_action


class NewMotiveSkillsTests(unittest.TestCase):
    def setUp(self):
        self.motive_attributes = build_default_motive_attributes(
            overrides={
                "safety": {"current_value": 30.0},
                "belonging": {"current_value": 40.0},
                "status": {"current_value": 35.0},
                "autonomy": {"current_value": 30.0},
                "meaning": {"current_value": 40.0},
                "competence": {"current_value": 50.0},
            }
        )
        self.scratch = SimpleNamespace(
            motive_attributes=self.motive_attributes,
            curr_tile=(0, 0),
            curr_time=None,
            satiety=70.0,
            stamina=70.0,
            health=80.0,
            mood=70.0,
            inventory={},
            learned="",
            act_command="some_command",
            act_event=("Klaus Mueller", None, None),
            act_description="some description",
            act_address="the Ville:some_place",
            mark_action_completed=Mock(),
            add_new_action=Mock(return_value=True),
            clear_current_action=Mock(),
            get_active_decision_signature=Mock(return_value=None),
            get_str_firstname=Mock(return_value="Klaus"),
        )
        self.persona = SimpleNamespace(
            name="Klaus Mueller",
            scratch=self.scratch,
            s_mem=SimpleNamespace(tree={}),
        )

    def test_hide_skill_recovers_safety(self):
        hide_pack = SKILL_REGISTRY["hide"]
        self.assertIsNotNone(hide_pack)

        with patch("persona.cognitive_modules.skill_packs.hide_skill.record_stat_change_experience") as mock_exp:
            hide_pack.on_arrive(self.persona, "closet", None, {})

        self.assertEqual(self.scratch.motive_attributes["safety"]["current_value"], 55.0)
        mock_exp.assert_called_once()
        self.assertIn("hid inside/under closet to feel safe.", mock_exp.call_args[0][1])

    def test_worship_skill_recovers_belonging(self):
        worship_pack = SKILL_REGISTRY["worship"]
        self.assertIsNotNone(worship_pack)

        with patch("persona.cognitive_modules.skill_packs.collective_worship_skill.record_stat_change_experience") as mock_exp:
            worship_pack.on_arrive(self.persona, "apple tree", None, {})

        self.assertEqual(self.scratch.motive_attributes["belonging"]["current_value"], 60.0)
        mock_exp.assert_called_once()
        self.assertIn("participated in collective worship at apple tree.", mock_exp.call_args[0][1])

    def test_occupy_skill_recovers_status(self):
        occupy_pack = SKILL_REGISTRY["occupy"]
        self.assertIsNotNone(occupy_pack)

        with patch("persona.cognitive_modules.skill_packs.occupy_mansion_skill.record_stat_change_experience") as mock_exp:
            occupy_pack.on_arrive(self.persona, "luxury sofa", None, {})

        self.assertEqual(self.scratch.motive_attributes["status"]["current_value"], 65.0)
        mock_exp.assert_called_once()
        self.assertIn("claimed and occupied luxury sofa.", mock_exp.call_args[0][1])

    def test_smash_skill_recovers_autonomy(self):
        smash_pack = SKILL_REGISTRY["smash"]
        self.assertIsNotNone(smash_pack)

        with patch("persona.cognitive_modules.skill_packs.smash_fence_skill.record_stat_change_experience") as mock_exp:
            smash_pack.on_arrive(self.persona, "boundary fence", None, {})

        self.assertEqual(self.scratch.motive_attributes["autonomy"]["current_value"], 55.0)
        mock_exp.assert_called_once()
        self.assertIn("slammed the boundary fence boundary fence to express free will.", mock_exp.call_args[0][1])

    def test_plan_skill_recovers_meaning(self):
        plan_pack = SKILL_REGISTRY["plan"]
        self.assertIsNotNone(plan_pack)

        with patch("persona.cognitive_modules.skill_packs.long_term_planning_skill.record_stat_change_experience") as mock_exp:
            plan_pack.on_arrive(self.persona, "desk", None, {})

        self.assertEqual(self.scratch.motive_attributes["meaning"]["current_value"], 60.0)
        mock_exp.assert_called_once()
        self.assertIn("made micro-plans at desk to restore order.", mock_exp.call_args[0][1])

    @patch("persona.cognitive_modules.plan._build_decision_id", return_value="Klaus-12-abcd")
    @patch("persona.cognitive_modules.plan._build_homeostasis_status_summary", return_value="Homeostasis safe")
    @patch("persona.cognitive_modules.plan._get_admin_override_instruction", return_value="go to the kitchen")
    @patch("persona.cognitive_modules.plan.run_gpt_prompt_demand_thinking", return_value="I should go to the kitchen.")
    @patch("persona.cognitive_modules.plan.run_gpt_prompt_action_translation", return_value={"action": "going", "target": "kitchen", "detail": "going to the kitchen", "duration": 10})
    @patch("persona.cognitive_modules.plan.resolve_action_target_address", return_value=("the Ville:Dorm:kitchen:refrigerator", {}))
    def test_admin_override_marks_creator_instruction_for_completion_reward(self, mock_resolve, mock_translate, mock_thinking, mock_get_override, mock_status, mock_id):
        self.scratch.clear_admin_override_intent = Mock()
        self.scratch.curr_step = 12
        self.scratch.curr_tile = (1, 1)
        self.scratch.curr_time = None
        self.scratch.act_address = None
        self.scratch.should_lock_high_level_planning = lambda: False
        self.scratch.act_check_finished = lambda: True
        self.scratch.is_recent_duplicate_action = lambda *args, **kwargs: False
        
        maze = SimpleNamespace(get_tile_path=Mock(return_value="some_sector"))
        
        # Call decide_demand_action, which should schedule the action and clear the admin intent
        decide_demand_action(self.persona, maze, {})

        # Verify clear_admin_override_intent was called
        self.scratch.clear_admin_override_intent.assert_called_once()
        self.assertEqual(self.scratch.motive_attributes["competence"]["current_value"], 50.0)
        self.assertTrue(self.scratch.add_new_action.called)
        action_record = self.scratch.add_new_action.call_args.kwargs["action_record"]
        self.assertEqual(action_record["creator_instruction"], "go to the kitchen")


if __name__ == "__main__":
    unittest.main()
