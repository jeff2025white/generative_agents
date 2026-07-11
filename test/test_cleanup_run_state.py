import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cleanup_run_state as cleanup_module


class CleanupRunStateTests(unittest.TestCase):
    def test_reset_runtime_logs_truncates_root_runtime_logs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_root = Path(temp_dir)
            first_log = logs_root / "decision_prompt_trace.jsonl"
            second_log = logs_root / "motive_monitor.jsonl"
            first_log.write_text("old trace\n", encoding="utf-8")
            second_log.write_text("old motive\n", encoding="utf-8")

            with patch.object(cleanup_module, "LOGS_DIR", logs_root):
                actions = cleanup_module.reset_runtime_logs()

            self.assertEqual(first_log.read_text(encoding="utf-8"), "")
            self.assertEqual(second_log.read_text(encoding="utf-8"), "")
            self.assertEqual(actions, [str(first_log), str(second_log)])

if __name__ == "__main__":
    unittest.main()
