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


def _format_sim_time(curr_time):
    if curr_time is None:
        return None
    if isinstance(curr_time, str):
        return curr_time
    try:
        return curr_time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(curr_time)


def build_log_context(persona=None, scratch=None, sim_code=None):
    scratch_obj = scratch or getattr(persona, "scratch", None)
    context = {}
    resolved_sim_code = sim_code
    if resolved_sim_code is None and persona is not None:
        resolved_sim_code = getattr(persona, "sim_code", None)
    if resolved_sim_code is None and scratch_obj is not None:
        resolved_sim_code = getattr(scratch_obj, "sim_code", None)
    if resolved_sim_code is not None:
        context["sim_code"] = resolved_sim_code
    if scratch_obj is not None and getattr(scratch_obj, "curr_step", None) is not None:
        context["curr_step"] = getattr(scratch_obj, "curr_step")
    sim_time = _format_sim_time(getattr(scratch_obj, "curr_time", None)) if scratch_obj is not None else None
    if sim_time is not None:
        context["sim_time"] = sim_time
    return context


def merge_log_context(payload, persona=None, scratch=None, sim_code=None):
    record = dict(payload or {})
    context = build_log_context(persona=persona, scratch=scratch, sim_code=sim_code)
    for key, value in context.items():
        record.setdefault(key, value)
    return record


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
