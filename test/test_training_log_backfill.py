import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from test.check_backfill_training_prep_logs import run_backfill


class TrainingLogBackfillTests(unittest.TestCase):
    """Covers dry-run and write-mode backfill behavior."""

    def test_run_backfill_dry_run_reports_changed_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "decision_training_prep.jsonl"
            log_path.write_text(
                json.dumps({
                    "event": "prompt_logged",
                    "decision_id": "old-1",
                    "persona": "Isabella Rodriguez",
                    "curr_step": 8,
                    "prompt_kind": "demand_thinking",
                    "final_prompt": "Decision Capsule: ...",
                }, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            summary = run_backfill(log_path, write=False)

            self.assertTrue(summary["exists"])
            self.assertEqual(summary["row_count"], 1)
            self.assertEqual(summary["changed_count"], 1)
            self.assertFalse(summary["wrote_changes"])

    def test_run_backfill_write_updates_file_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "decision_training_prep.jsonl"
            log_path.write_text(
                json.dumps({
                    "event": "decision_logged",
                    "decision_id": "old-2",
                    "persona": "Klaus Mueller",
                    "curr_step": 12,
                    "prompt_kind": "action_translation",
                    "decision": {"action": "Gather", "target": "refrigerator"},
                }, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            summary = run_backfill(log_path, write=True)
            rewritten = json.loads(log_path.read_text(encoding="utf-8").strip())

            self.assertEqual(summary["changed_count"], 1)
            self.assertTrue(summary["wrote_changes"])
            self.assertIsNotNone(summary["backup_path"])
            self.assertTrue(Path(summary["backup_path"]).exists())
            self.assertIn("schema_version", rewritten)
            self.assertIn("minimal_filter_enabled", rewritten)
            self.assertIn("minimal_filter_summary", rewritten)


if __name__ == "__main__":
    unittest.main()
