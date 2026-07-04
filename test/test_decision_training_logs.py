import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from persona.training.training_candidate_builder import (
    TRAINING_PREP_SCHEMA_VERSION,
    normalize_training_log_record,
    upgrade_training_log_record,
)


class DecisionTrainingLogTests(unittest.TestCase):
    """Covers the minimum training-prep log contract."""

    def test_normalize_training_log_record_contains_required_fields(self):
        record = normalize_training_log_record({
            "event": "decision_logged",
            "decision_id": "Isabella-61-abc123",
            "persona": "Isabella Rodriguez",
            "curr_step": 61,
            "prompt_kind": "joint_decision",
            "final_prompt": "Decision Capsule: ...",
            "prompt_hash": "abc123hash",
            "decision": {"action": "Gather", "target": "apple tree"},
            "constraint_hit": True,
            "retry_reason": "apple tree is invalid",
            "execution_outcome": "path_not_found",
            "minimal_filter_enabled": True,
            "minimal_filter_applied": True,
            "minimal_filter_summary": {"invalid_targets": ["apple tree"], "retry_triggered": True},
            "ts": "2026-07-03T12:00:00+08:00",
        })

        self.assertEqual(
            sorted(record.keys()),
            [
                "constraint_hit",
                "curr_step",
                "decision",
                "decision_id",
                "event",
                "execution_outcome",
                "final_prompt",
                "minimal_filter_applied",
                "minimal_filter_enabled",
                "minimal_filter_summary",
                "persona",
                "prompt_hash",
                "prompt_kind",
                "retry_reason",
                "schema_version",
                "ts",
            ],
        )
        self.assertEqual(record["schema_version"], TRAINING_PREP_SCHEMA_VERSION)

    def test_join_key_is_decision_id(self):
        records = [
            {"decision_id": "abc", "event": "prompt_logged"},
            {"decision_id": "abc", "event": "decision_logged"},
            {"decision_id": "abc", "event": "execution_logged"},
        ]

        self.assertEqual(len({row["decision_id"] for row in records}), 1)

    def test_upgrade_training_log_record_preserves_extra_fields_and_backfills_schema(self):
        upgraded = upgrade_training_log_record({
            "event": "prompt_logged",
            "decision_id": "old-1",
            "persona": "Isabella Rodriguez",
            "curr_step": 8,
            "prompt_kind": "demand_thinking",
            "final_prompt": "Decision Capsule: ...",
            "level": "info",
            "log": "training_dataset/decision_training_prep.jsonl",
        })

        self.assertEqual(upgraded["level"], "info")
        self.assertEqual(upgraded["log"], "training_dataset/decision_training_prep.jsonl")
        self.assertEqual(upgraded["minimal_filter_enabled"], False)
        self.assertEqual(upgraded["minimal_filter_applied"], False)
        self.assertEqual(upgraded["minimal_filter_summary"], {})
        self.assertEqual(upgraded["schema_version"], TRAINING_PREP_SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
