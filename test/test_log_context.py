import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from persona.cognitive_modules.debug_log import build_log_context, merge_log_context


class LogContextTests(unittest.TestCase):
    def test_build_log_context_extracts_sim_fields_from_persona(self):
        scratch = SimpleNamespace(
            curr_step=17,
            curr_time=datetime(2026, 7, 10, 8, 5, 0),
        )
        persona = SimpleNamespace(
            name="Klaus Mueller",
            sim_code="sim_20260710_113627",
            scratch=scratch,
        )

        context = build_log_context(persona=persona)

        self.assertEqual(context["sim_code"], "sim_20260710_113627")
        self.assertEqual(context["curr_step"], 17)
        self.assertEqual(context["sim_time"], "2026-07-10 08:05:00")

    def test_merge_log_context_keeps_explicit_payload_values(self):
        scratch = SimpleNamespace(
            curr_step=17,
            curr_time=datetime(2026, 7, 10, 8, 5, 0),
        )
        persona = SimpleNamespace(
            name="Klaus Mueller",
            sim_code="sim_from_persona",
            scratch=scratch,
        )

        payload = merge_log_context(
            {"sim_code": "sim_explicit", "curr_step": 99, "event": "demo"},
            persona=persona,
        )

        self.assertEqual(payload["sim_code"], "sim_explicit")
        self.assertEqual(payload["curr_step"], 99)
        self.assertEqual(payload["sim_time"], "2026-07-10 08:05:00")
        self.assertEqual(payload["event"], "demo")


if __name__ == "__main__":
    unittest.main()
