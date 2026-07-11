import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from llm_api_config import (
    DEFAULT_CLOUD_CHAT_CONFIG_NAME,
    DEFAULT_DECISION_CONFIG_NAME,
    DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
    DEFAULT_SOCIAL_CHAT_CONFIG_NAME,
    TASK_ROUTE_CONFIG_NAMES,
    get_default_cloud_chat_request_config,
    get_default_decision_request_config,
    get_default_social_chat_request_config,
    get_default_translation_request_config,
    get_request_config,
    get_task_route_config_name,
    get_task_route_request_config,
)


class DecisionRequestConfigTests(unittest.TestCase):
    def test_all_default_config_names_share_single_primary_switch(self):
        self.assertEqual(DEFAULT_PRIMARY_CLOUD_CONFIG_NAME, "zhipu_chat")
        self.assertEqual(DEFAULT_CLOUD_CHAT_CONFIG_NAME, DEFAULT_PRIMARY_CLOUD_CONFIG_NAME)
        self.assertEqual(DEFAULT_SOCIAL_CHAT_CONFIG_NAME, "bailian_chat")
        self.assertEqual(DEFAULT_DECISION_CONFIG_NAME, DEFAULT_PRIMARY_CLOUD_CONFIG_NAME)

    def test_task_route_names_default_to_primary_cloud_config(self):
        self.assertEqual(TASK_ROUTE_CONFIG_NAMES["general_chat"], "zhipu_chat")
        self.assertEqual(TASK_ROUTE_CONFIG_NAMES["social_chat"], "bailian_chat")
        self.assertEqual(TASK_ROUTE_CONFIG_NAMES["social_decision"], "zhipu_chat")
        self.assertEqual(TASK_ROUTE_CONFIG_NAMES["social_generation"], "zhipu_chat")
        self.assertEqual(TASK_ROUTE_CONFIG_NAMES["safety_scoring"], "zhipu_chat")
        self.assertEqual(TASK_ROUTE_CONFIG_NAMES["decision"], "zhipu_chat")
        self.assertEqual(TASK_ROUTE_CONFIG_NAMES["planning"], "zhipu_chat")
        self.assertEqual(TASK_ROUTE_CONFIG_NAMES["location_selection"], "zhipu_chat")
        self.assertEqual(TASK_ROUTE_CONFIG_NAMES["object_state"], "zhipu_chat")
        self.assertEqual(TASK_ROUTE_CONFIG_NAMES["memory_reflection"], "zhipu_chat")
        self.assertEqual(TASK_ROUTE_CONFIG_NAMES["translation"], "zhipu_chat")
        self.assertEqual(TASK_ROUTE_CONFIG_NAMES["event_triple"], "zhipu_chat")

    def test_get_task_route_request_config_returns_named_provider(self):
        self.assertEqual(
            get_task_route_request_config("decision"),
            get_request_config("zhipu_chat"),
        )

    def test_default_cloud_chat_request_config_defaults_to_zhipu_chat(self):
        self.assertEqual(
            get_default_cloud_chat_request_config(),
            get_request_config("zhipu_chat"),
        )

    def test_decision_request_config_defaults_to_zhipu_chat(self):
        self.assertEqual(
            get_default_decision_request_config(),
            get_request_config("zhipu_chat"),
        )

    def test_default_translation_request_config_defaults_to_zhipu_chat(self):
        self.assertEqual(
            get_default_translation_request_config(),
            get_request_config("zhipu_chat"),
        )

    def test_social_chat_request_config_can_be_switched_via_task_route(self):
        with patch.dict("llm_api_config.TASK_ROUTE_CONFIG_NAMES", {"social_chat": "bailian_chat"}, clear=False):
            self.assertEqual(
                get_default_social_chat_request_config(),
                get_request_config("bailian_chat"),
            )

    def test_social_chat_request_config_defaults_to_bailian_chat(self):
        self.assertEqual(
            get_default_social_chat_request_config(),
            get_request_config("bailian_chat"),
        )

    def test_decision_request_config_can_be_switched_via_task_route(self):
        with patch.dict("llm_api_config.TASK_ROUTE_CONFIG_NAMES", {"decision": "bailian_chat"}, clear=False):
            self.assertEqual(
                get_default_decision_request_config(),
                get_request_config("bailian_chat"),
            )

    def test_task_route_name_lookup_can_be_switched_directly(self):
        with patch.dict("llm_api_config.TASK_ROUTE_CONFIG_NAMES", {"translation": "bailian_chat"}, clear=False):
            self.assertEqual(get_task_route_config_name("translation"), "bailian_chat")
            self.assertEqual(
                get_task_route_request_config("translation"),
                get_request_config("bailian_chat"),
            )


if __name__ == "__main__":
    unittest.main()
