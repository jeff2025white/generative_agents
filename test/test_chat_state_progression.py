import datetime
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.dot = lambda *args, **kwargs: 0.0
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda *args, **kwargs: 1.0
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub
sys.modules.setdefault("openai", SimpleNamespace(api_key=None, api_base=None))

import persona.cognitive_modules.plan as plan_module
import persona.persona as persona_module
from persona.memory_structures.scratch import Scratch


class ChatStateProgressionTests(unittest.TestCase):
    def test_chat_action_finishes_once_current_time_passes_end_time(self):
        scratch = Scratch(str(ROOT / "test" / "__missing_chat_finish_guard__.json"))
        scratch.curr_time = datetime.datetime(2026, 7, 4, 12, 11, 0)
        scratch.act_address = "<persona> Maria Lopez"
        scratch.chatting_with = "Maria Lopez"
        scratch.chatting_end_time = datetime.datetime(2026, 7, 4, 12, 10, 0)

        self.assertTrue(scratch.act_check_finished())

    def test_chat_react_assigns_role_specific_descriptions(self):
        init_persona = SimpleNamespace(
            name="Klaus Mueller",
            scratch=SimpleNamespace(
                act_start_time=datetime.datetime(2026, 7, 4, 12, 0, 0),
                curr_time=datetime.datetime(2026, 7, 4, 12, 0, 0),
            ),
        )
        target_persona = SimpleNamespace(
            name="Maria Lopez",
            scratch=SimpleNamespace(
                act_start_time=datetime.datetime(2026, 7, 4, 12, 0, 0),
                curr_time=datetime.datetime(2026, 7, 4, 12, 0, 0),
            ),
        )
        inserted_acts = []

        def fake_create_react(persona, inserted_act, *args, **kwargs):
            inserted_acts.append((persona.name, inserted_act))

        with patch.object(plan_module, "_create_react", side_effect=fake_create_react), \
             patch.object(plan_module, "build_dialogue_id", return_value="dlg_test"), \
             patch.object(plan_module, "compute_social_opportunity_score", return_value={"score": 1}), \
             patch.object(plan_module, "compute_social_cooldown", return_value=3), \
             patch.object(plan_module, "set_social_dialogue_state"), \
             patch.object(plan_module, "log_social_decision"):
            plan_module._chat_react(
                maze=None,
                persona=init_persona,
                focused_event=SimpleNamespace(subject="Maria Lopez"),
                reaction_mode="chat with Maria Lopez",
                personas={"Klaus Mueller": init_persona, "Maria Lopez": target_persona},
            )

        self.assertEqual(
            inserted_acts,
            [
                ("Klaus Mueller", "having a conversation with Maria Lopez"),
                ("Maria Lopez", "having a conversation with Klaus Mueller"),
            ],
        )

    def test_fresh_explicit_decision_is_not_immediately_overridden_by_social_reaction(self):
        scratch = SimpleNamespace(
            act_description="",
            act_address=None,
            act_event=(None, None, None),
            act_command=None,
            act_start_time=None,
            curr_time=datetime.datetime(2026, 7, 4, 12, 0, 0),
            chatting_with=None,
            chat=None,
            chatting_end_time=None,
            should_lock_high_level_planning=lambda: False,
            act_check_finished=lambda: True,
            should_resume_suspended_action=lambda: False,
        )
        persona = SimpleNamespace(name="Maria Lopez", scratch=scratch)

        def decide(*_args, **_kwargs):
            scratch.act_description = "playing on the game console"
            scratch.act_address = "the Ville:Dorm:Klaus Mueller's room:game console"
            scratch.act_event = ("Maria Lopez", "leisure_use", "game console")
            scratch.act_command = {"source": "decision_translation", "skill_id": "leisure_use", "target": "game console"}
            scratch.act_start_time = scratch.curr_time

        with patch.object(plan_module, "decide_demand_action", side_effect=decide), \
             patch.object(plan_module, "_choose_retrieved", return_value=SimpleNamespace(subject="Isabella Rodriguez")), \
             patch.object(plan_module, "_should_react", return_value="chat with Isabella Rodriguez") as react_mock, \
             patch.object(plan_module, "clear_social_dialogue_state"), \
             patch.object(plan_module, "_decrement_chatting_with_buffer"):
            result = plan_module.plan(
                persona,
                maze=None,
                personas={},
                new_day=False,
                retrieved={"nearby": {"curr_event": SimpleNamespace(subject="Isabella Rodriguez")}},
            )

        self.assertEqual(result, scratch.act_address)
        react_mock.assert_not_called()

    def test_chat_react_does_not_override_target_fresh_explicit_decision(self):
        curr_time = datetime.datetime(2026, 7, 4, 12, 0, 0)
        init_persona = SimpleNamespace(
            name="Isabella Rodriguez",
            scratch=SimpleNamespace(act_command=None, act_start_time=curr_time, curr_time=curr_time),
        )
        target_persona = SimpleNamespace(
            name="Maria Lopez",
            scratch=SimpleNamespace(
                act_command={"source": "decision_translation", "skill_id": "leisure_use", "target": "game console"},
                act_start_time=curr_time,
                curr_time=curr_time,
                act_description="playing on the game console",
            ),
        )

        with patch.object(plan_module, "_create_react") as create_mock, \
             patch.object(plan_module, "append_debug_log") as log_mock:
            result = plan_module._chat_react(
                maze=None,
                persona=init_persona,
                focused_event=SimpleNamespace(subject="Maria Lopez"),
                reaction_mode="chat with Maria Lopez",
                personas={"Isabella Rodriguez": init_persona, "Maria Lopez": target_persona},
            )

        self.assertFalse(result)
        create_mock.assert_not_called()
        self.assertEqual(log_mock.call_args.args[1]["reason"], "fresh_explicit_decision")

    def test_physiological_crisis_wraps_active_chat_before_replanning(self):
        remembered = []
        logged = []
        scratch = SimpleNamespace(
            chatting_with="Maria Lopez",
            curr_time=datetime.datetime(2026, 7, 4, 12, 0, 0),
            satiety=22.0,
            stamina=55.0,
            health=90.0,
            act_description="having a conversation with Maria Lopez",
            chatting_end_time=datetime.datetime(2026, 7, 4, 12, 10, 0),
            act_duration=10,
            planned_path=[(1, 1)],
            act_path_set=True,
            last_action_desc=None,
            remember_pending_interrupt=lambda reason, source="system", payload=None: remembered.append(
                {"reason": reason, "source": source, "payload": payload or {}}
            ),
        )
        persona = SimpleNamespace(name="Klaus Mueller", scratch=scratch)

        with patch.object(persona_module, "log_social_dialogue", side_effect=lambda *args, **kwargs: logged.append((args, kwargs))):
            wrapped = persona_module._request_chat_wrap_for_physiological_crisis(persona)

        self.assertTrue(wrapped)
        self.assertEqual(scratch.chatting_end_time, scratch.curr_time)
        self.assertEqual(scratch.act_duration, 0)
        self.assertEqual(scratch.planned_path, [])
        self.assertFalse(scratch.act_path_set)
        self.assertIn("Wrapping up due to physiological need", scratch.last_action_desc)
        self.assertEqual(remembered[0]["reason"], "physiological_crisis_after_chat_wrap")
        self.assertEqual(logged[0][0][2], "dialogue_wrap_requested")


if __name__ == "__main__":
    unittest.main()
