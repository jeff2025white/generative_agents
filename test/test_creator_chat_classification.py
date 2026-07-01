import os
import sys
import unittest
from pathlib import Path


ROOT = Path(r"g:\generative_agents")
FRONTEND = ROOT / "environment" / "frontend_server"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "frontend_server.settings")

import django

django.setup()

from translator.views import classify_creator_message


class CreatorChatClassificationTests(unittest.TestCase):
    def test_query_message(self):
        payload = classify_creator_message("你现在在做什么？")
        self.assertEqual(payload["message_mode"], "query")

    def test_instruction_message(self):
        payload = classify_creator_message("先去厨房找吃的")
        self.assertEqual(payload["message_mode"], "instruction")

    def test_notify_message(self):
        payload = classify_creator_message("通知你，今晚八点 Maria 会来找你")
        self.assertEqual(payload["message_mode"], "notify")

    def test_default_mode_is_query(self):
        payload = classify_creator_message("最近好吗")
        self.assertEqual(payload["message_mode"], "query")


if __name__ == "__main__":
    unittest.main()
