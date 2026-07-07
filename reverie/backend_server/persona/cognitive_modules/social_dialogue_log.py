"""
Unified social dialogue logging helpers.
"""
import json
import os
import re

from persona.cognitive_modules.debug_log import append_debug_log


SOCIAL_DIALOGUE_LOG_NAME = "social_dialogue_debug.jsonl"
CHAT_TRANSCRIPT_LOG_NAME = "chat_transcript.jsonl"


def _project_root():
  return os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
  )


def _scoped_chat_transcript_path(sim_code):
  normalized_sim_code = str(sim_code or "").strip()
  if not normalized_sim_code:
    return None
  return os.path.join(
    _project_root(),
    "environment",
    "frontend_server",
    "storage",
    normalized_sim_code,
    CHAT_TRANSCRIPT_LOG_NAME,
  )


def _append_jsonl_record(path, record):
  if not path:
    return
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps(record, ensure_ascii=False, default=str, sort_keys=True) + "\n")


def _slug(value):
  """Convert display text into a compact ID-safe token."""
  cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip())
  cleaned = cleaned.strip("_")
  return cleaned or "unknown"


def build_dialogue_id(init_persona, target_persona):
  """Build a stable per-conversation dialogue identifier."""
  initiator = getattr(init_persona, "name", "unknown")
  target = getattr(target_persona, "name", "unknown")
  curr_time = getattr(getattr(init_persona, "scratch", None), "curr_time", None)
  curr_step = getattr(getattr(init_persona, "scratch", None), "curr_step", None)
  time_part = curr_time.strftime("%Y%m%d_%H%M%S") if curr_time else "unknown_time"
  step_part = curr_step if curr_step is not None else "na"
  return f"dlg_{_slug(initiator)}_{_slug(target)}_{time_part}_{step_part}"


def set_social_dialogue_state(persona, dialogue_id, partner_name=None, role=None, topic=None):
  """Persist current dialogue metadata in scratch for later stages."""
  persona.scratch.social_dialogue_id = dialogue_id
  persona.scratch.social_dialogue_partner = partner_name
  persona.scratch.social_dialogue_role = role
  persona.scratch.social_dialogue_started_step = getattr(persona.scratch, "curr_step", None)
  persona.scratch.social_dialogue_topic = topic


def inherit_social_dialogue_state(persona, source_persona, role=None):
  """Copy dialogue state from another persona when the same conversation is shared."""
  dialogue_id = getattr(source_persona.scratch, "social_dialogue_id", None)
  if not dialogue_id:
    return None
  set_social_dialogue_state(
    persona,
    dialogue_id,
    partner_name=getattr(source_persona, "name", None),
    role=role or getattr(source_persona.scratch, "social_dialogue_role", None),
    topic=getattr(source_persona.scratch, "social_dialogue_topic", None),
  )
  return dialogue_id


def clear_social_dialogue_state(persona):
  """Clear scratch dialogue metadata when the active social chat ends."""
  persona.scratch.social_dialogue_id = None
  persona.scratch.social_dialogue_partner = None
  persona.scratch.social_dialogue_role = None
  persona.scratch.social_dialogue_started_step = None
  persona.scratch.social_dialogue_topic = None


def get_social_dialogue_context(persona, target_name=None, dialogue_id=None):
  """Return a common context payload for social dialogue logging."""
  scratch = getattr(persona, "scratch", None)
  return {
    "dialogue_id": dialogue_id or getattr(scratch, "social_dialogue_id", None),
    "persona": getattr(persona, "name", None),
    "target": target_name or getattr(scratch, "social_dialogue_partner", None),
    "topic": getattr(scratch, "social_dialogue_topic", None),
    "sim_time": getattr(scratch, "curr_time", None),
    "step": getattr(scratch, "curr_step", None),
    "role": getattr(scratch, "social_dialogue_role", None),
    "sim_code": getattr(persona, "sim_code", None),
  }


def log_social_dialogue(persona, phase, event, target_name=None, dialogue_id=None, payload=None):
  """Append a unified social dialogue JSONL record."""
  record = get_social_dialogue_context(persona, target_name=target_name, dialogue_id=dialogue_id)
  record["phase"] = phase
  record["event"] = event
  if isinstance(payload, dict):
    record["payload"] = payload
  elif payload is not None:
    record["payload"] = {"value": payload}
  append_debug_log(SOCIAL_DIALOGUE_LOG_NAME, record)


def log_chat_transcript(persona, conversation, target_name=None, dialogue_id=None, channel="social", payload=None):
  """Persist full chat turns into a dedicated transcript log."""
  turns = []
  for row in conversation or []:
    if isinstance(row, (list, tuple)) and len(row) >= 2:
      turns.append({
        "speaker": row[0],
        "utterance": row[1],
      })
  record = get_social_dialogue_context(persona, target_name=target_name, dialogue_id=dialogue_id)
  record["phase"] = "transcript"
  record["event"] = "chat_transcript_written"
  record["channel"] = channel
  record["turn_count"] = len(turns)
  record["conversation"] = turns
  if isinstance(payload, dict):
    record["payload"] = payload
  elif payload is not None:
    record["payload"] = {"value": payload}
  append_debug_log(CHAT_TRANSCRIPT_LOG_NAME, record)
  scoped_log_path = _scoped_chat_transcript_path(record.get("sim_code"))
  _append_jsonl_record(scoped_log_path, record)
