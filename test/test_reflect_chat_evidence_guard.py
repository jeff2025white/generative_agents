import datetime
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch


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


import persona.cognitive_modules.reflect as reflect_module


class ReflectChatEvidenceGuardTests(unittest.TestCase):
    """Ensure reflection survives missing last-chat memory nodes."""

    def test_reflect_handles_missing_last_chat_node(self):
        curr_time = datetime.datetime(2026, 7, 2, 13, 0, 0)
        a_mem = SimpleNamespace(
            get_last_chat=lambda _name: False,
            add_thought=MagicMock(),
            seq_event=[],
            seq_thought=[],
        )
        scratch = SimpleNamespace(
            name="Maria Lopez",
            curr_time=curr_time,
            chatting_end_time=curr_time + datetime.timedelta(seconds=10),
            chat=[("Maria Lopez", "See you later.")],
            chatting_with="Klaus Mueller",
            social_dialogue_id=None,
        )
        persona = SimpleNamespace(a_mem=a_mem, scratch=scratch)

        with patch.object(reflect_module, "reflection_trigger", return_value=False), \
             patch.object(reflect_module, "generate_planning_thought_on_convo", return_value="Wrap up the conversation calmly."), \
             patch.object(reflect_module, "generate_memo_on_convo", return_value="will remember this chat positively."), \
             patch.object(reflect_module, "generate_action_event_triple", return_value=("Maria Lopez", "reflects on", "chat")), \
             patch.object(reflect_module, "generate_poig_score", return_value=1.0), \
             patch.object(reflect_module, "get_embedding", return_value=[0.1, 0.2]):
            reflect_module.reflect(persona)

        self.assertEqual(a_mem.add_thought.call_count, 2)
        first_evidence = a_mem.add_thought.call_args_list[0].args[-1]
        second_evidence = a_mem.add_thought.call_args_list[1].args[-1]
        self.assertEqual(first_evidence, [])
        self.assertEqual(second_evidence, [])

