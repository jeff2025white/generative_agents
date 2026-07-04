"""Dry-run and backfill utility for decision training-prep logs."""

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from persona.training.training_candidate_builder import upgrade_training_log_record


DEFAULT_LOG_PATH = ROOT / "logs" / "training_dataset" / "decision_training_prep.jsonl"


def load_jsonl_rows(log_path):
    """Load JSONL rows from the target log file."""
    rows = []
    for line_number, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        rows.append((line_number, json.loads(line)))
    return rows


def backfill_jsonl_rows(rows):
    """Upgrade all rows and report how many records changed."""
    upgraded_rows = []
    changed_count = 0
    for _, row in rows:
        upgraded = upgrade_training_log_record(row)
        if upgraded != row:
            changed_count += 1
        upgraded_rows.append(upgraded)
    return upgraded_rows, changed_count


def write_jsonl_rows(log_path, rows):
    """Rewrite JSONL rows in a deterministic UTF-8 format."""
    serialized = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
    log_path.write_text(serialized, encoding="utf-8")


def create_backup(log_path):
    """Create a timestamped backup before in-place migration."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = log_path.with_name(f"{log_path.stem}.backup_{timestamp}{log_path.suffix}")
    shutil.copy2(log_path, backup_path)
    return backup_path


def run_backfill(log_path, write=False):
    """Run the backfill in dry-run or write mode and return a summary."""
    if not log_path.exists():
        return {
            "log_path": str(log_path),
            "exists": False,
            "row_count": 0,
            "changed_count": 0,
            "backup_path": None,
            "wrote_changes": False,
        }

    source_rows = load_jsonl_rows(log_path)
    upgraded_rows, changed_count = backfill_jsonl_rows(source_rows)
    backup_path = None
    if write and changed_count:
      backup_path = create_backup(log_path)
      write_jsonl_rows(log_path, upgraded_rows)

    return {
        "log_path": str(log_path),
        "exists": True,
        "row_count": len(source_rows),
        "changed_count": changed_count,
        "backup_path": str(backup_path) if backup_path else None,
        "wrote_changes": bool(write and changed_count),
    }


def main():
    """CLI entry for dry-run and write-mode backfill."""
    parser = argparse.ArgumentParser(description="Backfill historical decision training-prep logs.")
    parser.add_argument("--path", default=str(DEFAULT_LOG_PATH), help="Target JSONL log path.")
    parser.add_argument("--write", action="store_true", help="Rewrite the file in place after creating a backup.")
    args = parser.parse_args()

    summary = run_backfill(Path(args.path), write=args.write)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
