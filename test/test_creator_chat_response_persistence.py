import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(r"g:\generative_agents")
FRONTEND = ROOT / "environment" / "frontend_server"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "frontend_server.settings")

import django

django.setup()

from translator.views import _resolve_pending_action_reply


class CreatorChatPersistenceTests(unittest.TestCase):
    def test_empty_response_is_not_treated_as_success(self):
        action = SimpleNamespace(status="replied", response="")
        result_type, payload = _resolve_pending_action_reply(action)
        self.assertEqual(result_type, "reply")
        self.assertIsNone(payload)

    def test_nonempty_response_is_returned(self):
        action = SimpleNamespace(status="replied", response="你好")
        result_type, payload = _resolve_pending_action_reply(action)
        self.assertEqual(result_type, "reply")
        self.assertEqual(payload, "你好")

    def test_failed_response_is_explicit(self):
        action = SimpleNamespace(status="failed", response="backend error")
        result_type, payload = _resolve_pending_action_reply(action)
        self.assertEqual(result_type, "__FAILED__")
        self.assertIn("backend error", payload)


if __name__ == "__main__":
    unittest.main()
