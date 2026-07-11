import tempfile
import unittest
from pathlib import Path

from logs.clear_runtime_logs import clear_runtime_logs, iter_runtime_log_paths


class ClearRuntimeLogsTests(unittest.TestCase):
    def test_iter_runtime_log_paths_includes_root_and_agent_logs_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_root = Path(temp_dir)
            root_log = logs_root / "decision_prompt_trace.jsonl"
            agent_log = logs_root / "agents" / "sim_001" / "Maria_Lopez.jsonl"
            training_log = logs_root / "training_dataset" / "action_translation_sft.jsonl"
            report_file = logs_root / "full_reasoning_step_chain.md"

            agent_log.parent.mkdir(parents=True, exist_ok=True)
            training_log.parent.mkdir(parents=True, exist_ok=True)

            root_log.write_text("root\n", encoding="utf-8")
            agent_log.write_text("agent\n", encoding="utf-8")
            training_log.write_text("dataset\n", encoding="utf-8")
            report_file.write_text("report\n", encoding="utf-8")

            discovered = iter_runtime_log_paths(logs_root)

            self.assertEqual(discovered, sorted([root_log, agent_log]))

    def test_clear_runtime_logs_preserves_training_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_root = Path(temp_dir)
            root_log = logs_root / "action_outcome.jsonl"
            agent_log = logs_root / "agents" / "sim_001" / "Isabella_Rodriguez.jsonl"
            training_log = logs_root / "training_dataset" / "decision_training_prep.jsonl"

            agent_log.parent.mkdir(parents=True, exist_ok=True)
            training_log.parent.mkdir(parents=True, exist_ok=True)

            root_log.write_text("runtime\n", encoding="utf-8")
            agent_log.write_text("agent\n", encoding="utf-8")
            training_log.write_text("dataset\n", encoding="utf-8")

            cleared = clear_runtime_logs(logs_root)

            self.assertEqual(root_log.read_text(encoding="utf-8"), "")
            self.assertEqual(agent_log.read_text(encoding="utf-8"), "")
            self.assertEqual(training_log.read_text(encoding="utf-8"), "dataset\n")
            self.assertEqual(cleared, [str(path) for path in sorted([root_log, agent_log])])


if __name__ == "__main__":
    unittest.main()
