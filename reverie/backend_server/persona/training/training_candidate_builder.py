"""Helpers for normalizing decision logs into training-prep records."""


TRAINING_PREP_LOG_NAME = "training_dataset/decision_training_prep.jsonl"
TRAINING_PREP_SCHEMA_VERSION = 2


def normalize_training_log_record(record):
  """Normalize decision training-prep records into one stable event schema."""
  data = dict(record or {})
  return {
    "event": data.get("event") or "decision_logged",
    "decision_id": data.get("decision_id"),
    "persona": data.get("persona"),
    "curr_step": data.get("curr_step"),
    "prompt_kind": data.get("prompt_kind"),
    "final_prompt": data.get("final_prompt"),
    "prompt_hash": data.get("prompt_hash"),
    "decision": data.get("decision"),
    "constraint_hit": bool(data.get("constraint_hit", False)),
    "retry_reason": data.get("retry_reason") or "",
    "execution_outcome": data.get("execution_outcome"),
    "minimal_filter_enabled": bool(data.get("minimal_filter_enabled", False)),
    "minimal_filter_applied": bool(data.get("minimal_filter_applied", False)),
    "minimal_filter_summary": data.get("minimal_filter_summary") or {},
    "schema_version": int(data.get("schema_version", TRAINING_PREP_SCHEMA_VERSION) or TRAINING_PREP_SCHEMA_VERSION),
    "ts": data.get("ts"),
  }


def upgrade_training_log_record(record):
  """Upgrade one training-prep record while preserving unknown metadata fields."""
  data = dict(record or {})
  normalized = normalize_training_log_record(data)
  upgraded = dict(data)
  upgraded.update(normalized)
  return upgraded
