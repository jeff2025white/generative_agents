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


if __name__ == "__main__":
    unittest.main()
