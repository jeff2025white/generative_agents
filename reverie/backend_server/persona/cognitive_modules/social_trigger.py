"""
Utilities for NPC-to-NPC social trigger decisions.
"""

from persona.cognitive_modules.action_command_utils import build_action_command, build_decision_signature
from persona.cognitive_modules.debug_log import append_debug_log


DEFAULT_SOCIAL_SCAN_INTERVAL = 5


def _clamp(value, min_value=0.0, max_value=1.0):
  """Clamp a float into a bounded range."""
  return max(min_value, min(max_value, value))


def _safe_lower(value):
  """Return a lowercase string for safe substring checks."""
  return str(value or "").strip().lower()


def _safe_name(target_persona):
  """Return the target persona name if available."""
  return getattr(target_persona, "name", "")


def _get_relationship_info(init_persona, target_persona):
  """Return relationship metadata between two personas."""
  try:
    rel = init_persona.a_mem.get_relationship(target_persona.name)
    if isinstance(rel, dict):
      return rel
  except Exception:
    pass
  return {}


def social_hard_block(init_persona, target_persona):
  """Return hard blocking reasons that should always forbid social chat."""
  reasons = []
  if not init_persona or not target_persona:
    reasons.append("missing_persona")
    return True, reasons
  if _safe_name(init_persona) == _safe_name(target_persona):
    reasons.append("self_target")
  if not getattr(target_persona.scratch, "act_address", None):
    reasons.append("target_missing_action_address")
  if not getattr(target_persona.scratch, "act_description", None):
    reasons.append("target_missing_action_description")
  if not getattr(init_persona.scratch, "act_address", None):
    reasons.append("self_missing_action_address")
  if not getattr(init_persona.scratch, "act_description", None):
    reasons.append("self_missing_action_description")
  if "sleeping" in _safe_lower(getattr(target_persona.scratch, "act_description", None)):
    reasons.append("target_sleeping")
  if "sleeping" in _safe_lower(getattr(init_persona.scratch, "act_description", None)):
    reasons.append("self_sleeping")

  self_chatting_with = getattr(init_persona.scratch, "chatting_with", None)
  target_chatting_with = getattr(target_persona.scratch, "chatting_with", None)
  if self_chatting_with and self_chatting_with != target_persona.name:
    reasons.append("self_busy_chatting")
  if target_chatting_with and target_chatting_with != init_persona.name:
    reasons.append("target_busy_chatting")
  return bool(reasons), reasons


def _distance_score(init_persona, target_persona):
  """Calculate a proximity score based on current tiles."""
  init_tile = getattr(init_persona.scratch, "curr_tile", None)
  target_tile = getattr(target_persona.scratch, "curr_tile", None)
  if not init_tile or not target_tile:
    return 0.02
  try:
    manhattan = abs(init_tile[0] - target_tile[0]) + abs(init_tile[1] - target_tile[1])
  except Exception:
    return 0.02
  if manhattan <= 1:
    return 0.28
  if manhattan <= 3:
    return 0.22
  if manhattan <= 6:
    return 0.14
  return 0.06


def _relationship_score(init_persona, target_persona):
  """Score how socially attractive the target is from relationship memory."""
  rel = _get_relationship_info(init_persona, target_persona)
  relation = _safe_lower(rel.get("relationship"))
  trust = float(rel.get("trust", 0.0) or 0.0)
  base = 0.05
  if relation in {"friend", "close_friend"}:
    base = 0.18
  elif relation in {"family", "partner"}:
    base = 0.22
  elif relation in {"coworker", "classmate", "acquaintance"}:
    base = 0.12
  return _clamp(base + min(0.12, max(0.0, trust) * 0.12), 0.0, 0.34)


def _relationship_penalty(init_persona, target_persona):
  """Penalize only socially cold or low-trust pairings that reduce talk likelihood."""
  rel = _get_relationship_info(init_persona, target_persona)
  relation = _safe_lower(rel.get("relationship"))
  trust = float(rel.get("trust", 0.0) or 0.0)

  penalty = 0.0
  if relation in {"stranger"} and trust <= 0.05:
    penalty += 0.03

  if relation not in {"enemy", "hostile"} and trust <= 0.0:
    penalty += 0.08
  elif relation not in {"enemy", "hostile"} and trust < 0.15:
    penalty += 0.04

  return min(0.18, penalty)


def _conflict_bonus(init_persona, target_persona):
  """Reward hostile contact that is likely to produce taunts or confrontation."""
  rel = _get_relationship_info(init_persona, target_persona)
  relation = _safe_lower(rel.get("relationship"))
  recent_events = [
    _safe_lower(event)
    for event in (rel.get("recent_events", []) or [])
  ]

  bonus = 0.0
  if relation in {"enemy", "hostile"}:
    bonus += 0.16
  if any(
    keyword in event
    for event in recent_events
    for keyword in ("robbed", "was robbed", "stole", "stolen", "betrayed", "threatened", "attacked")
  ):
    bonus += 0.10
  return min(0.24, bonus)


def _state_score(init_persona, target_persona):
  """Score whether both agents are in a state that is easy to interrupt."""
  init_desc = _safe_lower(getattr(init_persona.scratch, "act_description", None))
  target_desc = _safe_lower(getattr(target_persona.scratch, "act_description", None))
  target_addr = _safe_lower(getattr(target_persona.scratch, "act_address", None))
  score = 0.02
  if "idle" in init_desc or "relax" in init_desc:
    score += 0.06
  if "idle" in target_desc or "relax" in target_desc:
    score += 0.08
  if "<waiting>" in target_addr or "waiting" in target_desc:
    score += 0.12
  if "walking" in init_desc or "going" in init_desc:
    score += 0.02
  return _clamp(score, 0.0, 0.24)


def _novelty_bonus(target_persona, retrieved):
  """Reward recent memory context that specifically references the target."""
  if not retrieved:
    return 0.0
  target_name = _safe_lower(target_persona.name)
  hits = 0
  for bucket_name in ("events", "thoughts"):
    for node in retrieved.get(bucket_name, []) or []:
      desc = _safe_lower(getattr(node, "embedding_key", None) or getattr(node, "description", None))
      if target_name and target_name in desc:
        hits += 1
  curr_event = retrieved.get("curr_event")
  if curr_event and target_name in _safe_lower(getattr(curr_event, "description", None)):
    hits += 1
  return min(0.16, hits * 0.04)


def _social_need_bonus(init_persona):
  """Reward social interaction when the agent has not interacted recently."""
  score = 0.0
  mood = float(getattr(init_persona.scratch, "mood", 100.0) or 100.0)
  stamina = float(getattr(init_persona.scratch, "stamina", 100.0) or 100.0)
  if mood < 65:
    score += 0.05
  if stamina >= 35:
    score += 0.03
  last_social_time = getattr(init_persona.scratch, "last_social_time", None)
  curr_time = getattr(init_persona.scratch, "curr_time", None)
  if not last_social_time or not curr_time:
    score += 0.05
  else:
    try:
      minutes_since_social = (curr_time - last_social_time).total_seconds() / 60.0
      if minutes_since_social >= 120:
        score += 0.08
      elif minutes_since_social >= 45:
        score += 0.04
    except Exception:
      score += 0.03
  return _clamp(score, 0.0, 0.16)


def _recent_chat_penalty(init_persona, target_persona):
  """Return a soft penalty for recently chatting with the same target."""
  buffer_count = int((getattr(init_persona.scratch, "chatting_with_buffer", {}) or {}).get(target_persona.name, 0) or 0)
  if buffer_count <= 0:
    return 0.0
  return min(0.32, buffer_count / 400.0 * 0.16)


def _night_penalty(init_persona):
  """Reduce late-night conversation frequency without hard blocking it."""
  curr_time = getattr(init_persona.scratch, "curr_time", None)
  if not curr_time:
    return 0.0
  hour = curr_time.hour
  if hour >= 23 or hour < 6:
    return 0.18
  if hour >= 22:
    return 0.08
  return 0.0


def _urgency_penalty(init_persona):
  """Penalize social chat when the agent is in a physiological or work crunch."""
  satiety = float(getattr(init_persona.scratch, "satiety", 100.0) or 100.0)
  stamina = float(getattr(init_persona.scratch, "stamina", 100.0) or 100.0)
  act_desc = _safe_lower(getattr(init_persona.scratch, "act_description", None))
  penalty = 0.0
  if satiety < 35:
    penalty += 0.14
  if stamina < 35:
    penalty += 0.12
  if any(keyword in act_desc for keyword in ("cook", "gather", "eat", "consume", "study", "work")):
    penalty += 0.05
  return min(0.28, penalty)


def _switch_cost_penalty(init_persona, target_persona):
  """Penalize chat when it would interrupt an ongoing non-social commitment."""
  scratch = getattr(init_persona, "scratch", None)
  if not scratch:
    return 0.0
  chat_signature = build_decision_signature(
    build_action_command("chat with", _safe_name(target_persona), source="social_trigger", raw_action="chat with"),
    action_description=f"chatting with {_safe_name(target_persona)}",
  )
  try:
    return min(0.32, float(getattr(scratch, "compute_switch_cost", lambda _sig: 0.0)(chat_signature) or 0.0))
  except Exception:
    return 0.0


def _recent_duplicate_social_penalty(init_persona, target_persona):
  """Penalize immediately repeating the same social target after completion."""
  scratch = getattr(init_persona, "scratch", None)
  if not scratch:
    return 0.0
  chat_signature = build_decision_signature(
    build_action_command("chat with", _safe_name(target_persona), source="social_trigger", raw_action="chat with"),
    action_description=f"chatting with {_safe_name(target_persona)}",
  )
  try:
    is_dup = bool(getattr(scratch, "is_recent_duplicate_action", lambda _sig, within_steps=2: False)(chat_signature, within_steps=6))
  except Exception:
    is_dup = False
  return 0.12 if is_dup else 0.0


def compute_social_opportunity_score(init_persona, target_persona, retrieved):
  """Calculate a structured score that estimates chat likelihood."""
  detail = {
    "distance_score": _distance_score(init_persona, target_persona),
    "relationship_score": _relationship_score(init_persona, target_persona),
    "relationship_penalty": _relationship_penalty(init_persona, target_persona),
    "conflict_bonus": _conflict_bonus(init_persona, target_persona),
    "state_score": _state_score(init_persona, target_persona),
    "novelty_bonus": _novelty_bonus(target_persona, retrieved),
    "social_need_bonus": _social_need_bonus(init_persona),
    "recent_chat_penalty": _recent_chat_penalty(init_persona, target_persona),
    "recent_duplicate_penalty": _recent_duplicate_social_penalty(init_persona, target_persona),
    "night_penalty": _night_penalty(init_persona),
    "urgency_penalty": _urgency_penalty(init_persona),
    "switch_cost_penalty": _switch_cost_penalty(init_persona, target_persona),
  }
  total = (
    0.12
    + detail["distance_score"]
    + detail["relationship_score"]
    + detail["state_score"]
    + detail["novelty_bonus"]
    + detail["social_need_bonus"]
    + detail["conflict_bonus"]
    - detail["relationship_penalty"]
    - detail["recent_chat_penalty"]
    - detail["recent_duplicate_penalty"]
    - detail["night_penalty"]
    - detail["urgency_penalty"]
    - detail["switch_cost_penalty"]
  )
  detail["total"] = _clamp(total, 0.0, 1.0)
  return detail


def compute_social_cooldown(init_persona, target_persona, retrieved=None, score_detail=None):
  """Compute a dynamic cooldown after a conversation completes."""
  if score_detail is None:
    score_detail = compute_social_opportunity_score(init_persona, target_persona, retrieved or {})
  rel = _get_relationship_info(init_persona, target_persona)
  trust = float(rel.get("trust", 0.0) or 0.0)
  cooldown = 120
  cooldown -= int(min(45, max(0.0, trust) * 40))
  cooldown -= int(score_detail.get("novelty_bonus", 0.0) * 120)
  cooldown -= int(score_detail.get("state_score", 0.0) * 80)
  cooldown -= int(score_detail.get("conflict_bonus", 0.0) * 90)
  cooldown += int(score_detail.get("relationship_penalty", 0.0) * 180)
  cooldown += int(score_detail.get("night_penalty", 0.0) * 100)
  cooldown += int(score_detail.get("urgency_penalty", 0.0) * 80)
  return max(40, min(220, cooldown))


def should_auto_initiate_social_chat(score_detail):
  """Return True when a social opportunity is strong enough to bypass the LLM gate."""
  if not score_detail:
    return False
  total = float(score_detail.get("total", 0.0) or 0.0)
  urgency_penalty = float(score_detail.get("urgency_penalty", 0.0) or 0.0)
  novelty_bonus = float(score_detail.get("novelty_bonus", 0.0) or 0.0)
  state_score = float(score_detail.get("state_score", 0.0) or 0.0)
  social_need_bonus = float(score_detail.get("social_need_bonus", 0.0) or 0.0)

  if total >= 0.50 and urgency_penalty <= 0.08:
    return True
  if total >= 0.42 and urgency_penalty <= 0.08 and (
    novelty_bonus >= 0.12 or state_score >= 0.04 or social_need_bonus >= 0.08
  ):
    return True
  return False


def choose_social_focus(persona, retrieved, personas, min_score=0.24):
  """Pick the best nearby persona-related event for social reaction."""
  best_entry = None
  best_score = -1.0
  candidates = []
  for _, rel_ctx in (retrieved or {}).items():
    curr_event = rel_ctx.get("curr_event")
    if not curr_event:
      continue
    subject = getattr(curr_event, "subject", None)
    if not subject or ":" in subject or subject == persona.name or subject not in personas:
      continue
    target_persona = personas[subject]
    blocked, reasons = social_hard_block(persona, target_persona)
    score_detail = compute_social_opportunity_score(persona, target_persona, rel_ctx)
    candidates.append({
      "target": subject,
      "blocked": blocked,
      "reasons": reasons,
      "score": score_detail,
    })
    if not blocked and score_detail["total"] >= min_score and score_detail["total"] > best_score:
      best_entry = rel_ctx
      best_score = score_detail["total"]
  return best_entry, candidates


def log_social_decision(persona, target_name, event_name, payload):
  """Append a JSONL debug record for social trigger decisions."""
  record = {
    "persona": getattr(persona, "name", None),
    "target": target_name,
    "event": event_name,
    "curr_time": getattr(getattr(persona, "scratch", None), "curr_time", None),
    "curr_step": getattr(getattr(persona, "scratch", None), "curr_step", None),
  }
  if isinstance(payload, dict):
    record.update(payload)
  else:
    record["payload"] = payload
  append_debug_log("social_trigger_debug.jsonl", record)


def should_run_periodic_social_scan(persona, interval=DEFAULT_SOCIAL_SCAN_INTERVAL):
  """Return True when a moving persona should briefly reconsider social chat."""
  curr_step = getattr(persona.scratch, "curr_step", None)
  if curr_step is None or interval <= 0:
    return False
  defer_social_interrupts = getattr(persona.scratch, "should_defer_social_interrupts", None)
  if callable(defer_social_interrupts) and defer_social_interrupts():
    return False
  if getattr(persona.scratch, "chatting_with", None):
    return False
  if not getattr(persona.scratch, "planned_path", None):
    return False
  act_predicate = ""
  try:
    act_predicate = _safe_lower(persona.scratch.act_event[1])
  except Exception:
    act_predicate = ""
  if act_predicate in {"chat with", "creator_comm"}:
    return False
  return curr_step % interval == 0
