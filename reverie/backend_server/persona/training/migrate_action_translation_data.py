"""
Migrate existing action_translation records from decision_training_prep.jsonl
to the new action_translation_sft.jsonl format.

Usage:
    cd reverie/backend_server
    python -m persona.training.migrate_action_translation_data
"""
import json
import os
import sys

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from persona.training.action_translation_dataset import (
    DATASET_PATH,
    SYSTEM_MESSAGE,
    log_action_translation_pair,
)


def migrate():
    old_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "logs", "training_dataset", "decision_training_prep.jsonl")
    )
    if not os.path.exists(old_path):
        print(f"Source file not found: {old_path}")
        return

    # Phase 1: Index all records by decision_id
    prompts = {}   # decision_id -> prompt string
    decisions = {}  # decision_id -> decision dict + metadata

    with open(old_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue

            if record.get("prompt_kind") != "action_translation":
                continue

            did = record.get("decision_id", "")
            if not did:
                continue

            if record.get("event") == "prompt_logged" and record.get("final_prompt"):
                prompts[did] = record
            elif record.get("event") == "decision_logged" and record.get("decision"):
                decisions[did] = record

    # Phase 2: Match and write
    matched = set(prompts.keys()) & set(decisions.keys())
    print(f"Found {len(prompts)} prompts, {len(decisions)} decisions, {len(matched)} matched pairs")

    if not matched:
        print("No pairs to migrate.")
        return

    count = 0
    for did in sorted(matched):
        p = prompts[did]
        d = decisions[did]
        log_action_translation_pair(
            persona_name=p.get("persona", "unknown"),
            prompt=p["final_prompt"],
            decision=d["decision"],
            decision_id=did,
            step=d.get("curr_step"),
        )
        count += 1

    print(f"Migrated {count} pairs to {DATASET_PATH}")


if __name__ == "__main__":
    migrate()
