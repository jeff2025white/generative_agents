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
from llm_api_config import get_task_route_request_config
from persona.cognitive_modules.skill_packs.chat_skill import ChatSkillPack
from persona.cognitive_modules.skill_packs.cook_skill import CookSkillPack


class SkillPackRequestRouteTests(unittest.TestCase):
    def test_chat_skill_creator_mode_uses_general_chat_route(self):
        persona = SimpleNamespace(
            name="Maria Lopez",
            scratch=SimpleNamespace(
                act_address='<creator>{"id": 1, "action_type": "query", "content": "你现在在做什么？", "message_mode": "query", "conversation_history": []}',
            ),
        )
        expected_config = get_task_route_request_config("general_chat")

        with patch.object(chat_skill_module, "build_creator_query_context", return_value={
            "self_state": "idle",
            "environment": "kitchen",
            "plans": "none",
            "memories": "none",
            "relationships": "none",
            "history": "none",
        }), \
            patch.object(chat_skill_module, "generate_prompt", return_value="prompt"), \
            patch.object(ChatSkillPack, "run_skill_llm_request", return_value={
                "reply": "我正在厨房附近活动。",
                "emoji": "👁️",
                "next_action": "",
                "reasoning": "creator query",
            }) as mocked:
            result = ChatSkillPack().cognitive_decision(
                persona,
                target="none",
                maze=SimpleNamespace(),
                personas={},
            )

        self.assertEqual(result["mode"], "creator")
        self.assertEqual(mocked.call_args.kwargs["request_config"], expected_config)

    def test_chat_skill_monologue_mode_uses_general_chat_route(self):
        persona = SimpleNamespace(
            name="Maria Lopez",
            scratch=SimpleNamespace(
                act_address="",
                satiety=60.0,
                stamina=70.0,
                health=90.0,
                inventory={"apple": 1},
                act_description="walking home",
                get_str_iss=lambda: "Name: Maria Lopez",
            ),
        )
        expected_config = get_task_route_request_config("general_chat")

        with patch.object(chat_skill_module, "new_retrieve", return_value={
            "self": [SimpleNamespace(embedding_key="Maria remembers she still needs lunch.")]
        }), \
            patch.object(chat_skill_module, "generate_prompt", return_value="prompt"), \
            patch.object(ChatSkillPack, "run_skill_llm_request", return_value={
                "monologue": "先把眼前的事情做完。",
                "emoji": "💭",
            }) as mocked:
            result = ChatSkillPack().cognitive_decision(
                persona,
                target="none",
                maze=SimpleNamespace(),
                personas={},
            )

        self.assertEqual(result["mode"], "monologue")
        self.assertEqual(mocked.call_args.kwargs["request_config"], expected_config)

    def test_cook_skill_uses_general_chat_route(self):
        persona = SimpleNamespace(
            name="Maria Lopez",
            scratch=SimpleNamespace(
                inventory={"apple": 2},
            ),
        )
        expected_config = get_task_route_request_config("general_chat")

        with patch.object(CookSkillPack, "run_skill_llm_request", return_value={
            "dish": "baked apple",
            "monologue": "把苹果简单烤一下。",
        }) as mocked:
            result = CookSkillPack().cognitive_decision(
                persona,
                target="stove",
                maze=SimpleNamespace(),
                personas={},
            )

        self.assertEqual(result["dish"], "baked apple")
        self.assertEqual(mocked.call_args.kwargs["request_config"], expected_config)


if __name__ == "__main__":
    unittest.main()
