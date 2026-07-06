import sys
import unittest
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sys.modules.setdefault("openai", SimpleNamespace(api_key=None, api_base=None))
if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.dot = lambda *args, **kwargs: 0.0
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda *args, **kwargs: 1.0
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub

from persona.cognitive_modules.action_command_utils import (
    build_action_command,
    build_decision_signature,
)
from persona.memory_structures.scratch import Scratch


def load_consume_skill_pack():
    package_name = "persona.cognitive_modules.skill_packs"
    if package_name not in sys.modules:
        fake_package = ModuleType(package_name)
        fake_package.__path__ = [str(BACKEND_ROOT / "persona" / "cognitive_modules" / "skill_packs")]
        sys.modules[package_name] = fake_package

    base_module_name = f"{package_name}.base"
    if base_module_name not in sys.modules:
        base_module = ModuleType(base_module_name)

        class BaseSkillPack:
            def __init__(self):
                self.name = ""
                self.associated_xp = ""

        base_module.BaseSkillPack = BaseSkillPack
        sys.modules[base_module_name] = base_module

    module_name = "test_consume_skill_runtime"
    if module_name in sys.modules:
        return sys.modules[module_name].ConsumeSkillPack

    module_path = BACKEND_ROOT / "persona" / "cognitive_modules" / "skill_packs" / "consume_skill.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.ConsumeSkillPack


def load_generic_skill_pack():
    package_name = "persona.cognitive_modules.skill_packs"
    if package_name not in sys.modules:
        fake_package = ModuleType(package_name)
        fake_package.__path__ = [str(BACKEND_ROOT / "persona" / "cognitive_modules" / "skill_packs")]
        sys.modules[package_name] = fake_package

    base_module_name = f"{package_name}.base"
    if base_module_name not in sys.modules:
        base_module = ModuleType(base_module_name)

        class BaseSkillPack:
            def __init__(self):
                self.name = ""
                self.associated_xp = ""

        base_module.BaseSkillPack = BaseSkillPack
        sys.modules[base_module_name] = base_module

    module_name = "test_generic_skill_runtime"
    if module_name in sys.modules:
        return sys.modules[module_name].GenericActivitySkillPack

    module_path = BACKEND_ROOT / "persona" / "cognitive_modules" / "skill_packs" / "generic_activity_skill.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.GenericActivitySkillPack


ConsumeSkillPack = load_consume_skill_pack()
GenericActivitySkillPack = load_generic_skill_pack()


class DummyMaze:
    def access_tile(self, _tile):
        return {"game_object": "refrigerator"}


class DecisionStabilityTests(unittest.TestCase):
    def make_scratch(self):
        scratch = Scratch(str(ROOT / "test" / "__missing_scratch__.json"))
        scratch.name = "Maria Lopez"
        scratch.first_name = "Maria"
        scratch.curr_time = datetime(2026, 7, 1, 8, 0, 0)
        scratch.curr_step = 100
        scratch.stamina = 80.0
        scratch.satiety = 70.0
        return scratch

    def add_action(self, scratch, skill_id, target, description, event_verb=None):
        event_verb = event_verb or skill_id
        return scratch.add_new_action(
            f"the Ville:Dorm for Oak Hill College:kitchen:{target}",
            10,
            description,
            "X",
            (scratch.name, event_verb, target),
            build_action_command(skill_id, target, source="decision_translation", raw_action=skill_id, detail=description),
            None,
            None,
            {},
            None,
            None,
            None,
            (None, None, None),
            scratch.curr_time,
        )

    def test_commit_window_blocks_unrelated_switch_without_stamina_penalty(self):
        scratch = self.make_scratch()

        accepted = self.add_action(
            scratch,
            "gather",
            "refrigerator",
            "opening the refrigerator to gather food items",
            event_verb="gather",
        )
        self.assertTrue(accepted)
        self.assertEqual(scratch.stamina, 80.0)

        scratch.curr_step += 1
        scratch.curr_time += timedelta(minutes=1)
        blocked = self.add_action(
            scratch,
            "work",
            "desk",
            "working at the desk on a study task",
            event_verb="work",
        )

        self.assertFalse(blocked)
        self.assertEqual(scratch.stamina, 80.0)
        self.assertEqual(scratch.act_command["skill_id"], "gather")
        self.assertEqual(scratch.last_decision_signature["intent_family"], "restore_satiety")

    def test_critical_survival_switch_bypasses_commit_window(self):
        scratch = self.make_scratch()
        self.add_action(
            scratch,
            "work",
            "desk",
            "working at the desk on a study task",
            event_verb="work",
        )

        scratch.curr_step += 1
        scratch.curr_time += timedelta(minutes=1)
        scratch.stamina = 20.0
        accepted = self.add_action(
            scratch,
            "rest",
            "bed",
            "lying down on the bed to recover stamina",
            event_verb="rest",
        )

        self.assertTrue(accepted)
        self.assertEqual(scratch.act_command["skill_id"], "rest")
        self.assertEqual(scratch.last_decision_signature["intent_family"], "restore_stamina")

    def test_same_family_internal_oscillation_is_blocked_within_commit_window(self):
        scratch = self.make_scratch()
        accepted = self.add_action(
            scratch,
            "consume",
            "refrigerator",
            "consuming food from the refrigerator",
            event_verb="consume",
        )
        self.assertTrue(accepted)

        scratch.curr_step += 1
        scratch.curr_time += timedelta(minutes=1)
        blocked = self.add_action(
            scratch,
            "gather",
            "refrigerator",
            "opening the refrigerator to gather food items",
            event_verb="gather",
        )

        self.assertFalse(blocked)
        self.assertEqual(scratch.last_decision_signature["skill_id"], "consume")
        self.assertEqual(scratch.last_decision_signature["intent_family"], "restore_satiety")

    def test_switch_cost_penalizes_interrupting_committed_work_for_chat(self):
        scratch = self.make_scratch()
        self.add_action(
            scratch,
            "work",
            "desk",
            "working at the desk on a study task",
            event_verb="work",
        )

        scratch.curr_step += 1
        scratch.curr_time += timedelta(minutes=1)
        chat_signature = build_decision_signature(
            build_action_command("chat with", "Klaus Mueller", source="social_trigger", raw_action="chat with")
        )

        penalty = scratch.compute_switch_cost(chat_signature)

        self.assertGreaterEqual(penalty, 0.2)

    def test_switch_cost_penalizes_same_family_internal_oscillation(self):
        scratch = self.make_scratch()
        self.add_action(
            scratch,
            "consume",
            "refrigerator",
            "consuming food from the refrigerator",
            event_verb="consume",
        )
        scratch.curr_step += 1
        scratch.curr_time += timedelta(minutes=1)
        gather_signature = build_decision_signature(
            build_action_command("gather", "refrigerator", source="decision_translation", raw_action="gather")
        )

        penalty = scratch.compute_switch_cost(gather_signature)

        self.assertGreaterEqual(penalty, 0.25)

    def test_physiological_interrupt_does_not_break_active_survival_route(self):
        scratch = self.make_scratch()
        scratch.satiety = 20.0
        self.add_action(
            scratch,
            "gather",
            "refrigerator",
            "opening the refrigerator to gather food items",
            event_verb="gather",
        )
        scratch.planned_path = [(1, 1), (1, 2)]

        self.assertFalse(scratch.should_interrupt_for_physiological_crisis())
        self.assertTrue(scratch.should_defer_social_interrupts())

    def test_physiological_interrupt_breaks_irrelevant_committed_route(self):
        scratch = self.make_scratch()
        scratch.satiety = 20.0
        self.add_action(
            scratch,
            "work",
            "desk",
            "working quietly at the desk",
            event_verb="work",
        )
        scratch.planned_path = [(1, 1), (1, 2)]

        self.assertTrue(scratch.should_interrupt_for_physiological_crisis())

    def test_suspend_and_resume_restores_previous_plan_with_fresh_path(self):
        scratch = self.make_scratch()
        self.add_action(
            scratch,
            "work",
            "desk",
            "working quietly at the desk",
            event_verb="work",
        )
        scratch.planned_path = [(1, 1), (1, 2)]

        suspended = scratch.suspend_current_action("physiological_crisis", source="test")
        scratch.clear_current_action()
        scratch.curr_step += 2
        scratch.curr_time += timedelta(minutes=2)
        resumed = scratch.resume_suspended_action()

        self.assertTrue(suspended)
        self.assertTrue(resumed)
        self.assertEqual(scratch.act_command["skill_id"], "work")
        self.assertEqual(scratch.act_description, "working quietly at the desk")
        self.assertEqual(scratch.planned_path, [])
        self.assertFalse(scratch.act_path_set)
        self.assertIsNone(scratch.suspended_action)

    def test_consume_skill_blocks_recent_duplicate_resource_consume(self):
        scratch = SimpleNamespace(
            inventory={"apple": 0},
            curr_step=12,
            recent_completed_action_signature=build_decision_signature(
                build_action_command("consume", "refrigerator", source="test", raw_action="consume")
            ),
            recent_completed_action_step=11,
            act_address="the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
            curr_tile=(1, 1),
        )
        persona = SimpleNamespace(name="Maria Lopez", scratch=scratch)
        skill = ConsumeSkillPack()

        can_execute = skill.can_execute(persona, "refrigerator", DummyMaze())

        self.assertFalse(can_execute)

    def test_generic_skill_blocks_recent_duplicate_action(self):
        scratch = SimpleNamespace(
            curr_step=20,
            recent_completed_action_signature=build_decision_signature(
                build_action_command("work", "desk", source="test", raw_action="work")
            ),
            recent_completed_action_step=19,
            act_address="the Ville:Oak Hill College:library:desk",
            is_recent_duplicate_action=lambda action_signature, within_steps=2: action_signature == build_decision_signature(
                build_action_command("work", "desk", source="test", raw_action="work")
            ),
        )
        persona = SimpleNamespace(name="Maria Lopez", scratch=scratch)
        skill = GenericActivitySkillPack("work", {"stamina": -5.0, "mood": -1.0})

        can_execute = skill.can_execute(persona, "desk", DummyMaze())

        self.assertFalse(can_execute)


if __name__ == "__main__":
    unittest.main()
