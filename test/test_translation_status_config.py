import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(r"g:\generative_agents")
FRONTEND = ROOT / "environment" / "frontend_server"
BACKEND = ROOT / "reverie" / "backend_server"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "frontend_server.settings")

import django

django.setup()

import translator.views as translator_views
from llm_api_config import (
    get_default_cloud_chat_request_config,
    get_status_translation_config,
)


class TranslationStatusConfigTests(unittest.TestCase):
    def setUp(self):
        self.original_cache = translator_views._status_translation_config
        translator_views._status_translation_config = None

    def tearDown(self):
        translator_views._status_translation_config = self.original_cache

    def test_status_translation_config_falls_back_to_central_project_config(self):
        with patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "",
                "DEEPSEEK_API_BASE": "",
                "DEEPSEEK_MODEL": "",
            },
            clear=False,
        ):
            config = translator_views._get_status_translation_config()

        self.assertEqual(config, get_status_translation_config())
        self.assertEqual(config, get_default_cloud_chat_request_config())

    def test_status_translation_config_prefers_environment_override(self):
        with patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "env-key",
                "DEEPSEEK_API_BASE": "https://env.example/v1",
                "DEEPSEEK_MODEL": "env-model",
            },
            clear=False,
        ):
            translator_views._status_translation_config = None
            config = translator_views._get_status_translation_config()

        self.assertEqual(
            config,
            {
                "api_key": "env-key",
                "api_base": "https://env.example/v1",
                "model": "env-model",
            },
        )


if __name__ == "__main__":
    unittest.main()
