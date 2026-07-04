import datetime
import json
import os

from persona.training.training_candidate_builder import (
    TRAINING_PREP_LOG_NAME,
    normalize_training_log_record,
)


def _logs_dir():
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "logs")
    )


def normalize_log_name(log_name):
    if not log_name:
        return "debug.jsonl"
    if log_name.endswith(".jsonl"):
        return log_name
    if log_name.endswith(".log"):
        return f"{log_name[:-4]}.jsonl"
    return f"{log_name}.jsonl"


def append_debug_log(log_name, payload, level="info"):
    os.makedirs(_logs_dir(), exist_ok=True)
    normalized_log_name = normalize_log_name(log_name)
    log_path = os.path.join(_logs_dir(), normalized_log_name)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    real_time = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat()
    if isinstance(payload, dict):
        record = dict(payload)
    else:
        record = {"message": str(payload)}
    if normalized_log_name == TRAINING_PREP_LOG_NAME:
        record = normalize_training_log_record(record)
    record.setdefault("ts", real_time)
    record.setdefault("level", level)
    record.setdefault("log", normalized_log_name)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str, sort_keys=True) + "\n")


def is_log_enabled(env_var_name, default=False):
    raw_value = os.environ.get(env_var_name)
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def safe_json_dumps(data):
    try:
        return json.dumps(data, ensure_ascii=False, default=str, sort_keys=True)
    except Exception:
        return str(data)
