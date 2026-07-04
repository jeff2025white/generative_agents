import time

from persona.cognitive_modules.debug_log import append_debug_log
from persona.cognitive_modules.retrieve import new_retrieve


INTENT_MEMORY_LOG = "intent_memory_retrieval.jsonl"

_INTENT_KEYWORDS = {
  "restore_satiety": {
    "food", "eat", "eating", "consume", "consume food", "gather",
    "refrigerator", "apple", "meal", "snack", "stove", "cafe counter",
    "hungry", "hunger", "satiety", "apple tree", "cooked meal",
  },
  "restore_stamina": {
    "rest", "sleep", "sleeping", "nap", "bed", "sofa", "stamina",
    "energy", "recover", "recovery", "idle",
  },
  "restore_health": {
    "health", "healthy", "heal", "healing", "recover", "recovery",
    "treatment", "medicine", "rest", "safer", "injury",
  },
  "restore_mood": {
    "mood", "happy", "calm", "comfort", "comforting", "relax",
    "leisure", "music", "social", "joy", "recovery",
  },
}

_ATTRIBUTE_PRIORITY_THRESHOLDS = {
  "satiety": 50.0,
  "stamina": 50.0,
  "health": 70.0,
  "mood": 60.0,
}


def _normalize_text(value):
  return " ".join(str(value or "").strip().lower().split())


def _family_still_needs_attention(persona, intent_family):
  thresholds = _ATTRIBUTE_PRIORITY_THRESHOLDS
  scratch = getattr(persona, "scratch", None)
  if not scratch:
    return False
  if intent_family == "restore_satiety":
    return getattr(scratch, "satiety", 100.0) < thresholds["satiety"]
  if intent_family == "restore_stamina":
    return getattr(scratch, "stamina", 100.0) < thresholds["stamina"]
  if intent_family == "restore_health":
    return getattr(scratch, "health", 100.0) < thresholds["health"]
  if intent_family == "restore_mood":
    return getattr(scratch, "mood", 100.0) < thresholds["mood"]
  return False


def infer_memory_focus(persona, action_signature=None):
  signature = action_signature or {}
  intent_family = signature.get("intent_family")
  if intent_family in {"restore_satiety", "restore_stamina", "restore_health", "restore_mood"}:
    return intent_family

  recent_signature = getattr(persona.scratch, "recent_completed_action_signature", None) or {}
  recent_family = recent_signature.get("intent_family")

  if getattr(persona.scratch, "satiety", 100.0) < 40.0:
    return "restore_satiety"
  if getattr(persona.scratch, "stamina", 100.0) < 40.0:
    return "restore_stamina"
  if getattr(persona.scratch, "health", 100.0) < 70.0:
    return "restore_health"
  mood = float(getattr(persona.scratch, "mood", 100.0) or 100.0)
  satiety = float(getattr(persona.scratch, "satiety", 100.0) or 100.0)
  stamina = float(getattr(persona.scratch, "stamina", 100.0) or 100.0)
  health = float(getattr(persona.scratch, "health", 100.0) or 100.0)
  if mood < 50.0:
    return "restore_mood"
  if mood < 60.0 and satiety >= 70.0 and stamina >= 50.0 and health >= 70.0:
    return "restore_mood"
  if recent_family in {"restore_satiety", "restore_stamina", "restore_health", "restore_mood"}:
    if _family_still_needs_attention(persona, recent_family):
      return recent_family
  return None


def build_intent_focal_points(persona, intent_family, action_signature=None):
  firstname = persona.scratch.get_str_firstname() if hasattr(persona.scratch, "get_str_firstname") else persona.name
  if intent_family == "restore_satiety":
    return [
      f"Recent successful ways for {firstname} to restore satiety",
      f"Recent food-related outcomes for {firstname}",
      f"Known food sources near {firstname}",
      f"What happened the last time {firstname} tried to get food",
    ]
  if intent_family == "restore_stamina":
    return [
      f"Recent successful ways for {firstname} to restore stamina",
      f"Known resting places near {firstname}",
      f"Recent rest outcomes for {firstname}",
      f"What happened the last time {firstname} tried to recover energy",
    ]
  if intent_family == "restore_health":
    return [
      f"Recent successful ways for {firstname} to restore health",
      f"Recent health recovery outcomes for {firstname}",
      f"What helped {firstname} recover physically",
      f"What happened the last time {firstname} needed to recover health",
    ]
  if intent_family == "restore_mood":
    return [
      f"Recent successful ways for {firstname} to restore mood",
      f"Recent emotionally restorative outcomes for {firstname}",
      f"What activities helped {firstname} feel better",
      f"What happened the last time {firstname} recovered from low mood",
    ]
  return []


def _node_intent_bonus(node, intent_family):
  keywords = _INTENT_KEYWORDS.get(intent_family, set())
  haystacks = [
    _normalize_text(getattr(node, "description", "")),
    _normalize_text(getattr(node, "subject", "")),
    _normalize_text(getattr(node, "predicate", "")),
    _normalize_text(getattr(node, "object", "")),
    " ".join(sorted(_normalize_text(kw) for kw in getattr(node, "keywords", set()))),
  ]
  combined = " ".join(haystacks)
  bonus = 0.0
  for kw in keywords:
    if kw in combined:
      bonus += 2.5
  if getattr(node, "type", None) == "event":
    bonus += 0.75
  return bonus


def _flatten_unique_nodes(retrieved):
  ordered = []
  seen = set()
  for _focal_point, nodes in (retrieved or {}).items():
    for rank, node in enumerate(nodes):
      node_id = getattr(node, "node_id", None)
      if node_id in seen:
        continue
      seen.add(node_id)
      ordered.append((rank, node))
  return ordered


def _build_attribute_preferences(persona, intent_family=None):
  preferences = {}
  scratch = getattr(persona, "scratch", None)
  if not scratch:
    return preferences
  for attr_name, threshold in _ATTRIBUTE_PRIORITY_THRESHOLDS.items():
    current_value = float(getattr(scratch, attr_name, 100.0) or 100.0)
    if current_value < threshold:
      preferences[attr_name] = round((threshold - current_value) / threshold, 3)
  if intent_family == "restore_satiety":
    preferences["satiety"] = max(preferences.get("satiety", 0.0), 1.0)
  elif intent_family == "restore_stamina":
    preferences["stamina"] = max(preferences.get("stamina", 0.0), 1.0)
  elif intent_family == "restore_health":
    preferences["health"] = max(preferences.get("health", 0.0), 1.0)
  elif intent_family == "restore_mood":
    preferences["mood"] = max(preferences.get("mood", 0.0), 1.0)
  return preferences


def _node_attribute_bonus(node, attribute_preferences):
  attribute_effects = getattr(node, "attribute_effects", None) or {}
  if not attribute_preferences or not isinstance(attribute_effects, dict):
    return 0.0
  bonus = 0.0
  for attr_name, preference_weight in attribute_preferences.items():
    delta = float(attribute_effects.get(attr_name, 0.0) or 0.0)
    if delta == 0.0:
      continue
    normalized_delta = min(abs(delta), 40.0) / 40.0
    signed_weight = 1.0 if delta > 0 else -0.75
    bonus += preference_weight * normalized_delta * 6.0 * signed_weight
  return bonus


def rerank_by_intent(retrieved, intent_family, n_count=5, attribute_preferences=None):
  attribute_preferences = attribute_preferences or {}
  scored = []
  for rank, node in _flatten_unique_nodes(retrieved):
    recency_hint = max(0.0, 2.0 - (rank * 0.2))
    score = _node_intent_bonus(node, intent_family) + recency_hint
    score += float(getattr(node, "poignancy", 0.0) or 0.0) * 0.05
    score += _node_attribute_bonus(node, attribute_preferences)
    scored.append((score, node))
  scored.sort(key=lambda item: item[0], reverse=True)
  return [node for score, node in scored[:n_count]]


def summarize_intent_memories(intent_family, retrieved_nodes, max_items=4, max_chars=420):
  if not intent_family or not retrieved_nodes:
    return ""

  label_map = {
    "restore_satiety": "food-related experience",
    "restore_stamina": "recovery-related experience",
    "restore_health": "health-related experience",
    "restore_mood": "mood-related experience",
  }
  label = label_map.get(intent_family, "relevant experience")
  lines = [f"Relevant prior {label}:"]
  for node in retrieved_nodes[:max_items]:
    description = str(getattr(node, "description", "") or "").strip()
    if not description:
      continue
    lines.append(f"- {description}")
  summary = "\n".join(lines)
  if len(summary) > max_chars:
    summary = summary[:max_chars - 15].rstrip() + "...(truncated)"
  return summary


def retrieve_intent_memories(persona, intent_family, action_signature=None, n_count=5):
  if not intent_family:
    return []
  if not getattr(persona, "a_mem", None):
    return []
  if not (persona.a_mem.seq_event or persona.a_mem.seq_thought):
    return []

  focal_points = build_intent_focal_points(persona, intent_family, action_signature)
  if not focal_points:
    return []

  started_at = time.perf_counter()
  raw_retrieved = new_retrieve(persona, focal_points, n_count=max(n_count, 6))
  attribute_preferences = _build_attribute_preferences(persona, intent_family)
  reranked = rerank_by_intent(
    raw_retrieved,
    intent_family,
    n_count=n_count,
    attribute_preferences=attribute_preferences,
  )
  summary = summarize_intent_memories(intent_family, reranked)
  append_debug_log(
    INTENT_MEMORY_LOG,
    {
      "persona": getattr(persona, "name", None),
      "curr_step": getattr(persona.scratch, "curr_step", None),
      "intent_family": intent_family,
      "focal_points": focal_points,
      "selected_memory_ids": [getattr(node, "node_id", None) for node in reranked],
      "selected_memory_descriptions": [getattr(node, "description", "") for node in reranked],
      "attribute_preferences": attribute_preferences,
      "summary_chars": len(summary),
      "duration_ms": round((time.perf_counter() - started_at) * 1000.0, 3),
    }
  )
  return reranked
