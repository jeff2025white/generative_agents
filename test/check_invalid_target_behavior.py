import json
from collections import defaultdict
from pathlib import Path


LOG_PATH = Path("g:/generative_agents/logs/training_dataset/decision_training_prep.jsonl")


def main():
    grouped = defaultdict(list)
    if not LOG_PATH.exists():
        print("decisions=0")
        return

    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        decision_id = row.get("decision_id")
        if not decision_id:
            continue
        grouped[decision_id].append(row)

    constraint_hits = 0
    minimal_filter_enabled = 0
    minimal_filter_applied = 0
    repeated_failed_target_decisions = 0
    for rows in grouped.values():
        last_retry_reason = ""
        for row in rows:
            if row.get("constraint_hit"):
                constraint_hits += 1
            if row.get("minimal_filter_enabled"):
                minimal_filter_enabled += 1
            if row.get("minimal_filter_applied"):
                minimal_filter_applied += 1
            retry_reason = str(row.get("retry_reason") or "")
            if "invalid for this step" in retry_reason:
                last_retry_reason = retry_reason.lower()
            decision = row.get("decision") or {}
            target = str(decision.get("target") or "").strip().lower()
            if target and target in last_retry_reason:
                repeated_failed_target_decisions += 1

    print(f"decisions={len(grouped)}")
    print(f"constraint_hits={constraint_hits}")
    print(f"minimal_filter_enabled={minimal_filter_enabled}")
    print(f"minimal_filter_applied={minimal_filter_applied}")
    print(f"repeated_failed_target_decisions={repeated_failed_target_decisions}")


if __name__ == "__main__":
    main()
