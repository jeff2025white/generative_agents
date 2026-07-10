import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cleanup_run_state as cleanup_module


class CleanupRunStateTests(unittest.TestCase):
    def test_reset_transient_logs_only_truncates_declared_transient_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_root = Path(temp_dir)
            transient = logs_root / "decision_prompt_trace.jsonl"
            preserved = logs_root / "motive_monitor.jsonl"
            transient.write_text("old trace\n", encoding="utf-8")
            preserved.write_text("keep me\n", encoding="utf-8")

            with patch.object(cleanup_module, "LOGS_DIR", logs_root), \
                 patch.object(cleanup_module, "TRANSIENT_LOGS", ["decision_prompt_trace.jsonl"]):
                actions = cleanup_module.reset_transient_logs()

            self.assertEqual(transient.read_text(encoding="utf-8"), "")
            self.assertEqual(preserved.read_text(encoding="utf-8"), "keep me\n")
            self.assertEqual(actions, [str(transient)])

    def test_reset_scoped_chat_transcripts_truncates_all_run_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir) / "environment" / "frontend_server" / "storage"
            first = storage_root / "sim_a" / "chat_transcript.jsonl"
            second = storage_root / "sim_b" / "chat_transcript.jsonl"
            first.parent.mkdir(parents=True, exist_ok=True)
            second.parent.mkdir(parents=True, exist_ok=True)
            first.write_text("old a\n", encoding="utf-8")
            second.write_text("old b\n", encoding="utf-8")

            with patch.object(cleanup_module, "FRONTEND_STORAGE_DIR", storage_root):
                actions = cleanup_module.reset_scoped_chat_transcripts()

            self.assertEqual(first.read_text(encoding="utf-8"), "")
            self.assertEqual(second.read_text(encoding="utf-8"), "")
            self.assertEqual(sorted(actions), sorted([str(first), str(second)]))


if __name__ == "__main__":
    unittest.main()
