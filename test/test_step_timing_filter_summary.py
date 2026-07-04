import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


import persona.cognitive_modules.plan as plan_module


class StepTimingFilterSummaryTests(unittest.TestCase):
    def test_log_timing_event_keeps_minimal_filter_summary_fields(self):
        with patch.object(plan_module, "append_debug_log") as log_mock:
            plan_module._log_timing_event(
                "decide_demand_action_timing",
                {
                    "persona": "Isabella Rodriguez",
                    "curr_step": 54,
                    "total_ms": 123.0,
                    "timings_ms": {"joint_decision": 12.0},
                    "minimal_filter_enabled": True,
                    "minimal_filter_applied": True,
                    "minimal_filter_summary": {"invalid_targets": ["apple tree"]},
                },
            )

        payload = log_mock.call_args.args[1]
        self.assertEqual(payload["event"], "decide_demand_action_timing")
        self.assertEqual(payload["minimal_filter_enabled"], True)
        self.assertEqual(payload["minimal_filter_applied"], True)
        self.assertEqual(payload["minimal_filter_summary"]["invalid_targets"], ["apple tree"])


if __name__ == "__main__":
    unittest.main()
