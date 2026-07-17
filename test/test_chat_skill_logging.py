import datetime as dt
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


if "openai" not in sys.modules:
    openai_stub = SimpleNamespace(
        api_key=None,
        api_base=None,
        ChatCompletion=SimpleNamespace(create=lambda **kwargs: {"choices": [{"message": {"content": "stub"}}]}),
        Embedding=SimpleNamespace(create=lambda **kwargs: {"data": [{"embedding": [0.0]}]}),
    )
    sys.modules["openai"] = openai_stub


import persona.cognitive_modules.skill_packs.chat_skill as chat_skill_module
from persona.cognitive_modules.action_command_utils import build_action_command
from persona.cognitive_modules.skill_packs.chat_skill import ChatSkillPack
from persona.cognitive_modules.social_dialogue_log import set_social_dialogue_state
from persona.memory_structures.scratch import Scratch


class FakeMemory:
    def __init__(self):
        self.relationships = {}
        self.events = []
        self.seq_chat = []
        self._node_index = 0

    def get_relationship(self, name):
        return self.relationships.get(name)

    def update_relationship(self, name, relation_type=None, trust_delta=0.0, trust_absolute=None, recent_event=None):
        rel = dict(self.relationships.get(name) or {"relationship": "acquaintance", "trust": 0.5, "recent_events": []})
        if relation_type:
            rel["relationship"] = relation_type
        if trust_absolute is not None:
            rel["trust"] = float(trust_absolute)
        else:
            rel["trust"] = max(0.0, min(1.0, float(rel.get("trust", 0.0)) + float(trust_delta or 0.0)))
        if recent_event:
            rel.setdefault("recent_events", []).append(recent_event)
        self.relationships[name] = rel

    def add_event(self, *args, **kwargs):
        self._node_index += 1
        node = SimpleNamespace(node_id=f"node_{self._node_index}", args=args, kwargs=kwargs)
        self.events.append(node)
        return node


class FakeMaze:
    collision_maze = [[0]]

    def get_tile_path(self, tile, level):
        _ = tile
        _ = level
        return "test_arena"

    def access_tile(self, tile):
        _ = tile
        return {"collision": False, "game_object": "test bench", "sector": "Oak Hill", "arena": "Hobbs Cafe"}


class FakePersona:
    def __init__(self, name, tile):
        self.name = name
        self.sim_code = "test_chat_skill_logging"
        self.a_mem = FakeMemory()
        self.s_mem = SimpleNamespace(find_nearest_object=lambda _target: None)
        self.scratch = Scratch("__missing_test_chat_skill_logging__.json")
        self.scratch.name = name
        self.scratch.first_name = name.split()[0]
        self.scratch.last_name = name.split()[-1]
        self.scratch.innate = "friendly, curious"
        self.scratch.learned = f"{name} likes talking with other townspeople."
        self.scratch.currently = f"{name} is spending time near Hobbs Cafe."
        self.scratch.curr_time = dt.datetime(2026, 7, 11, 8, 12, 30)
        self.scratch.curr_step = 75
        self.scratch.curr_tile = list(tile)
        self.scratch.chatting_with_buffer = {}
        self.scratch.satiety = 34.0
        self.scratch.stamina = 88.0
        self.scratch.health = 100.0
        self.scratch.mood = 49.0
        self.scratch.act_description = "having a conversation"
        self.scratch.planned_path = []
        self.scratch.social_dialogue_topic = "talking about food access at Hobbs Cafe"
        self.scratch.act_command = {
            "detail": "talking about food access at Hobbs Cafe",
            "target": "Isabella Rodriguez",
        }
        self.scratch.skills.setdefault("cooking", {"level": 1, "xp": 0})
        self.scratch.skills.setdefault("gathering", {"level": 1, "xp": 0})
        self.scratch.skills.setdefault("singing", {"level": 1, "xp": 0})


def prime_chat_action(initiator, target):
    initiator.scratch.add_new_action(
        f"<persona> {target.name}",
        10,
        f"having a conversation with {target.name}",
        "💬",
        (initiator.name, "chat with", target.name),
        build_action_command("chat with", target.name, source="test_logging", raw_action="chat with"),
        target.name,
        None,
        {},
        initiator.scratch.curr_time + dt.timedelta(minutes=10),
        None,
        None,
        (None, None, None),
        initiator.scratch.curr_time,
    )
    initiator.scratch.act_path_set = True
    initiator.scratch.planned_path = []
    initiator.scratch.survival_applied = False
    set_social_dialogue_state(initiator, "dlg_test_chat_skill_logging", partner_name=target.name, role="init")


class ChatSkillLoggingTests(unittest.TestCase):
    def test_social_generation_logs_prompt_and_reply(self):
        initiator = FakePersona("Klaus Mueller", (0, 0))
        target = FakePersona("Isabella Rodriguez", (0, 0))
        initiator.scratch.social_dialogue_id = "dlg_test_turn_log"
        personas = {initiator.name: initiator, target.name: target}

        with patch.object(chat_skill_module, "new_retrieve", return_value={}), \
            patch.object(chat_skill_module, "compute_social_chat_turn_limit", return_value=1), \
            patch.object(chat_skill_module, "generate_prompt", return_value="PROMPT"), \
            patch.object(chat_skill_module, "log_social_dialogue") as mocked_log, \
            patch.object(ChatSkillPack, "run_skill_llm_request", return_value={
                "utterance": "你这儿还有巧克力饼干吗？",
                "end": True,
                "reasoning": "直接回应食物话题",
            }):
            result = ChatSkillPack().cognitive_decision(
                initiator,
                target=target.name,
                maze=FakeMaze(),
                personas=personas,
            )

        self.assertEqual(result["mode"], "social")
        self.assertEqual(result["convo"][0][1], "你这儿还有巧克力饼干吗？")
        self.assertTrue(mocked_log.called)
        self.assertEqual(mocked_log.call_args.kwargs["dialogue_id"], "dlg_test_turn_log")
        self.assertEqual(mocked_log.call_args.kwargs["prompt"], "PROMPT")
        self.assertEqual(
            mocked_log.call_args.kwargs["model_output"]["utterance"],
            "你这儿还有巧克力饼干吗？",
        )

    def test_on_arrive_logs_completed_transcript(self):
        initiator = FakePersona("Klaus Mueller", (0, 0))
        target = FakePersona("Maria Lopez", (0, 0))
        personas = {
            initiator.name: initiator,
            target.name: target,
        }
        prime_chat_action(initiator, target)
        fixed_convo = [
            [initiator.name, "你好，玛丽亚，今天过得怎么样？"],
            [target.name, "还不错，我刚在附近转了一圈。"],
            [initiator.name, "那挺好，等会儿一起去喝杯咖啡吧。"],
            [target.name, "好啊，我正想歇会儿。"],
        ]

        with patch.object(
            ChatSkillPack,
            "cognitive_decision",
            return_value={
                "mode": "social",
                "convo": fixed_convo,
                "target_persona_name": target.name,
            },
        ), patch(
            "persona.cognitive_modules.skill_packs.chat_skill.get_embedding",
            return_value=[0.0],
        ), patch(
            "persona.prompt_template.run_gpt_prompt.run_gpt_prompt_summarize_conversation",
            return_value=("两人聊了咖啡和休息安排。", None),
        ), patch(
            "persona.prompt_template.gpt_structure.ChatGPT_single_request",
            return_value="none",
        ), patch(
            "persona.cognitive_modules.skill_packs.chat_skill.log_chat_transcript",
        ) as mocked_transcript:
            ChatSkillPack().on_arrive(initiator, target.name, FakeMaze(), personas)

        self.assertTrue(mocked_transcript.called)
        self.assertEqual(
            mocked_transcript.call_args.kwargs["dialogue_id"],
            "dlg_test_chat_skill_logging",
        )
        self.assertEqual(mocked_transcript.call_args.kwargs["convo"], fixed_convo)
        self.assertEqual(
            mocked_transcript.call_args.kwargs["convo_summary"],
            "两人聊了咖啡和休息安排。",
        )
        initiator_rel = initiator.a_mem.get_relationship(target.name)
        target_rel = target.a_mem.get_relationship(initiator.name)
        self.assertIsNotNone(initiator_rel)
        self.assertIsNotNone(target_rel)
        self.assertGreater(initiator_rel["trust"], 0.5)
        self.assertGreater(target_rel["trust"], 0.5)
        self.assertTrue(
            any(node.args[5] == "两人聊了咖啡和休息安排。" for node in initiator.a_mem.events)
        )
        self.assertTrue(
            any(node.args[5] == "两人聊了咖啡和休息安排。" for node in target.a_mem.events)
        )
        self.assertTrue(
            any(
                "felt better after talking with" in node.args[5]
                and node.kwargs.get("attribute_effects", {}).get("mood") == 1.0
                for node in initiator.a_mem.events
            )
        )
        outcome = initiator.scratch.action_outcome_history[-1]
        self.assertEqual(outcome["execution"]["result"], "success")
        self.assertEqual(outcome["effects"]["self_attribute_effects"]["mood"], 1.0)
        self.assertEqual(outcome["effects"]["self_attribute_effects"]["stamina"], 4.0)


if __name__ == "__main__":
    unittest.main()
