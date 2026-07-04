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
from llm_api_config import get_default_social_chat_request_config, get_request_config
from persona.cognitive_modules.skill_packs.chat_skill import (
    SOCIAL_CHAT_REQUEST_CONFIG,
    collect_social_chat_memory_keys,
    filter_social_chat_recent_events,
    is_structurally_valid_social_chat_response,
    is_valid_social_chat_response,
    normalize_social_chat_response,
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


if __name__ == "__main__":
    unittest.main()
