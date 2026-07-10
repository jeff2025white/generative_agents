import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
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

if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda a: sum(x * x for x in a) ** 0.5
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub


import persona.cognitive_modules.skill_packs.chat_skill as chat_skill_module
from llm_api_config import get_default_social_chat_request_config, get_request_config
from persona.cognitive_modules.skill_packs.chat_skill import (
    SOCIAL_CHAT_REQUEST_CONFIG,
    apply_social_relationship_effect,
    collect_social_chat_memory_keys,
    compute_social_chat_turn_limit,
    format_social_chat_state,
    filter_social_chat_recent_events,
    is_structurally_valid_social_chat_response,
    is_valid_social_chat_response,
    normalize_social_chat_response,
    should_wait_for_dialogue_owner,
)
from persona.cognitive_modules.social_trigger import (
    compute_social_cooldown,
    compute_social_opportunity_score,
)


def make_node(description, embedding_key=None):
    return SimpleNamespace(
        description=description,
        embedding_key=embedding_key or description,
    )


class ChatSkillGuardTests(unittest.TestCase):
    def test_default_social_chat_request_config_comes_from_central_config(self):
        self.assertEqual(SOCIAL_CHAT_REQUEST_CONFIG, get_default_social_chat_request_config())
        self.assertEqual(SOCIAL_CHAT_REQUEST_CONFIG, get_request_config("deepseek_chat"))

    def test_bailian_chat_request_config_is_available(self):
        self.assertEqual(
            get_request_config("bailian_chat"),
            {
                "api_key": "sk-ws-H.RXEXPRM.V7xV.MEUCIQCX_Ht-mq4d9JvazH5E1ylm78Ethrks6UmDyOsEzEfdiAIgQ68FlOQTwKKExJ5pfftcJC8c3wI7n9DG9lU6Aevbvmk",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus-character",
            },
        )

    def test_collect_social_chat_memory_keys_filters_polluted_markers(self):
        retrieved = {
            "listener": [
                make_node("Maria Lopez is getting prepared food from the cafe counter"),
                make_node("For Maria Lopez's planning: should remember that Jamie helped set up the booth during the spontaneous downpour and shared about a new project that could benefit Alex's work."),
                make_node("Initiator-Speaker's ISS: ISS01, name: Alex. Interlocutor's name and traits: Name: Jamie."),
            ],
            "town": [
                make_node("Klaus Mueller consumed apple and restored physical condition."),
            ],
        }

        kept, dropped = collect_social_chat_memory_keys(retrieved)

        self.assertEqual(
            kept,
            [
                "Maria Lopez is getting prepared food from the cafe counter",
                "Klaus Mueller consumed apple and restored physical condition.",
            ],
        )
        self.assertEqual(len(dropped), 2)
        self.assertTrue(any("Alex" in item for item in dropped))

    def test_is_valid_social_chat_response_requires_chinese_text(self):
        self.assertTrue(
            is_structurally_valid_social_chat_response(
                {"utterance": "Hey Maria, have you heard the news?", "end": False}
            )
        )
        self.assertFalse(
            is_valid_social_chat_response(
                {"utterance": "Hey Maria, have you heard the news?", "end": False}
            )
        )
        self.assertTrue(
            is_valid_social_chat_response(
                {"utterance": "玛丽亚，你听说最近的消息了吗？", "end": False}
            )
        )

    def test_filter_social_chat_recent_events_drops_polluted_and_self_chat_text(self):
        kept, dropped = filter_social_chat_recent_events(
            [
                "shared lunch after the cafe shift",
                "conversing about Alex and Jamie discussing new project opportunities during their second meeting at the annual tech conference in Vegas last year",
                "Klaus Mueller is having a conversation with Klaus Mueller",
            ]
        )

        self.assertEqual(kept, ["shared lunch after the cafe shift"])
        self.assertEqual(len(dropped), 2)

    def test_normalize_social_chat_response_translates_english_json(self):
        original = {"utterance": "Hey Maria, have you heard the news?", "end": False, "reasoning": "share gossip"}
        translated = {"utterance": "玛丽亚，你听说最近的消息了吗？", "end": False, "reasoning": "翻译成中文"}

        with patch.object(chat_skill_module, "ChatGPT_safe_generate_response", return_value=translated) as mocked:
            result = normalize_social_chat_response(original, {"utterance": "你好！", "end": False})

        self.assertEqual(result, translated)
        mocked.assert_called_once()
        translation_prompt = mocked.call_args.args[0]
        special_instruction = mocked.call_args.args[2]
        self.assertIn("尽量简短", translation_prompt)
        self.assertIn("减少 AI 味", translation_prompt)
        self.assertIn("brief colloquial Simplified Chinese", special_instruction)

    def test_compute_social_chat_turn_limit_scales_with_relationship_and_topic_heat(self):
        target = SimpleNamespace(name="Maria Lopez")
        low_persona = SimpleNamespace(
            name="Klaus Mueller",
            a_mem=SimpleNamespace(get_relationship=lambda _name: None),
        )
        high_persona = SimpleNamespace(
            name="Klaus Mueller",
            a_mem=SimpleNamespace(
                get_relationship=lambda _name: {
                    "relationship": "friend",
                    "trust": 0.92,
                    "recent_events": ["talked about the party", "shared town gossip"],
                }
            ),
        )

        low_limit = compute_social_chat_turn_limit(
            low_persona,
            target,
            memory_keys=["hello"],
            recent_events=[],
        )
        high_limit = compute_social_chat_turn_limit(
            high_persona,
            target,
            memory_keys=["news", "rumor", "town", "party", "project"],
            recent_events=["shared town gossip", "party planning", "new project"],
        )

        self.assertGreaterEqual(low_limit, 3)
        self.assertLessEqual(high_limit, 8)
        self.assertLess(low_limit, high_limit)

    def test_should_wait_for_dialogue_owner_when_target_arrives_before_chat_ready(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                social_dialogue_id="dlg_1",
                social_dialogue_role="target",
            )
        )
        target = SimpleNamespace(
            scratch=SimpleNamespace(
                social_dialogue_id="dlg_1",
                social_dialogue_role="init",
                chat=None,
            )
        )

        self.assertTrue(should_wait_for_dialogue_owner(persona, target))

        target.scratch.chat = [["Klaus Mueller", "你好"]]
        self.assertFalse(should_wait_for_dialogue_owner(persona, target))

    def test_apply_social_relationship_effect_updates_only_current_persona(self):
        persona_updates = []
        target_updates = []
        persona = SimpleNamespace(
            name="Klaus Mueller",
            a_mem=SimpleNamespace(
                get_relationship=lambda _name: None,
                update_relationship=lambda *args, **kwargs: persona_updates.append((args, kwargs)),
            ),
        )
        target = SimpleNamespace(
            name="Maria Lopez",
            a_mem=SimpleNamespace(
                get_relationship=lambda _name: None,
                update_relationship=lambda *args, **kwargs: target_updates.append((args, kwargs)),
            ),
        )

        apply_social_relationship_effect(persona, target, "They had a pleasant chat.", trust_delta=0.02)

        self.assertEqual(len(persona_updates), 1)
        self.assertEqual(len(target_updates), 0)
        args, kwargs = persona_updates[0]
        self.assertEqual(args[0], "Maria Lopez")
        self.assertEqual(kwargs["trust_delta"], 0.02)

    def test_format_social_chat_state_uses_motive_priority_tags(self):
        persona = SimpleNamespace(
            name="Klaus Mueller",
            scratch=SimpleNamespace(
                curr_time=None,
                act_description="reading quietly",
                planned_path=[],
                satiety=62.0,
                stamina=75.0,
                health=90.0,
                mood=34.0,
                get_motive_attributes_snapshot=lambda: {
                    "satiety": {"current_value": 62.0, "initial_value": 60.0, "safe_threshold": 50.0, "critical_threshold": 25.0},
                    "stamina": {"current_value": 75.0, "initial_value": 75.0, "safe_threshold": 45.0, "critical_threshold": 20.0},
                    "health": {"current_value": 90.0, "initial_value": 85.0, "safe_threshold": 55.0, "critical_threshold": 25.0},
                    "mood": {"current_value": 34.0, "initial_value": 60.0, "safe_threshold": 50.0, "critical_threshold": 30.0},
                },
            ),
        )

        state_summary = format_social_chat_state(persona)

        self.assertIn("pressure=low_mood", state_summary)

    def test_enemy_relationship_after_robbery_can_still_trigger_hostile_social_contact(self):
        init_persona = SimpleNamespace(
            name="Klaus Mueller",
            scratch=SimpleNamespace(
                curr_tile=(0, 0),
                act_address="the Ville:Dorm:room",
                act_description="idling in the room",
                chatting_with=None,
                mood=55.0,
                stamina=80.0,
                satiety=80.0,
                last_social_time=None,
                curr_time=None,
                chatting_with_buffer={},
                compute_switch_cost=lambda _sig: 0.0,
                is_recent_duplicate_action=lambda _sig, within_steps=6: False,
            ),
            a_mem=SimpleNamespace(
                get_relationship=lambda _name: {
                    "relationship": "enemy",
                    "trust": 0.0,
                    "recent_events": ["was robbed of apple", "betrayed during a food dispute"],
                }
            ),
        )
        target_persona = SimpleNamespace(
            name="Maria Lopez",
            scratch=SimpleNamespace(
                curr_tile=(1, 0),
                act_address="the Ville:Dorm:hall",
                act_description="idling quietly",
                chatting_with=None,
            ),
        )

        score_detail = compute_social_opportunity_score(init_persona, target_persona, {})
        cooldown = compute_social_cooldown(init_persona, target_persona, score_detail=score_detail)

        self.assertGreaterEqual(score_detail["conflict_bonus"], 0.20)
        self.assertLessEqual(score_detail["relationship_penalty"], 0.08)
        self.assertGreater(score_detail["total"], 0.30)
        self.assertLess(cooldown, 120)


if __name__ == "__main__":
    unittest.main()
