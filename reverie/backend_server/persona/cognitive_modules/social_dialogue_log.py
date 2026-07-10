"""
Unified social dialogue logging helpers.
"""
import re


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
