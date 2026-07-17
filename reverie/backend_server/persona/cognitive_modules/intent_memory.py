import time

from persona.cognitive_modules.debug_log import append_debug_log, merge_log_context
from persona.cognitive_modules.retrieve import new_retrieve


INTENT_MEMORY_LOG = "intent_memory_retrieval.jsonl"

_INTENT_KEYWORDS = {
  "restore_satiety": {
    "food", "eat", "eating", "consume", "consume food", "gather",
    "refrigerator", "apple", "meal", "snack", "stove", "cafe counter",
    "hungry", "hunger", "satiety", "apple tree", "cooked meal",
    "inventory", "stock", "empty", "depleted", "forage", "wild",
    "failed", "unreachable", "path_not_found", "navigation_failure",
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

_MOTIVE_MEMORY_GROUPS = (
  ("satiety", "饱食 / 食物"),
  ("stamina", "精力 / 休息"),
  ("health", "健康 / 恢复"),
  ("safety", "安全 / 避险"),
  ("mood", "情绪 / 娱乐"),
  ("belonging", "归属 / 社交"),
  ("status", "地位 / 展示"),
  ("autonomy", "自主 / 控制"),
  ("competence", "胜任 / 学习工作"),
  ("meaning", "意义 / 反思"),
)
_MOTIVE_MEMORY_KEYWORDS = {
  "satiety": _INTENT_KEYWORDS["restore_satiety"],
  "stamina": _INTENT_KEYWORDS["restore_stamina"],
  "health": _INTENT_KEYWORDS["restore_health"],
  "safety": {"safe", "safety", "danger", "threat", "hide", "avoid", "escape"},
  "mood": _INTENT_KEYWORDS["restore_mood"],
  "belonging": {"social", "chat", "friend", "belong", "together", "company", "conversation"},
  "status": {"status", "respect", "recognition", "reputation", "prestige", "claim", "occupy"},
  "autonomy": {"autonomy", "control", "independent", "freedom", "pressure", "smash"},
  "competence": {"competence", "work", "study", "learn", "teach", "skill", "capable"},
  "meaning": {"meaning", "purpose", "plan", "reflect", "worship", "order"},
}

_MOTIVE_FOCAL_TOPICS = {
  "satiety": ("food access", "eating or gathering food", "food source failures"),
  "stamina": ("rest and sleep", "energy recovery", "rest failures"),
  "health": ("treatment and recovery", "health protection", "health recovery failures"),
  "safety": ("safety and danger avoidance", "safe shelter", "threat or escape outcomes"),
  "mood": ("emotional recovery", "leisure and comfort", "mood repair outcomes"),
  "belonging": ("social connection", "companionship and conversation", "social rejection or success"),
  "status": ("recognition and standing", "public achievement", "status gains or losses"),
  "autonomy": ("personal control", "independence and access", "blocked control or successful agency"),
  "competence": ("learning and effective work", "skill improvement", "work or study outcomes"),
  "meaning": ("purpose and reflection", "long-term direction", "meaningful activity outcomes"),
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


def build_motive_focal_points(persona, motive_key):
  firstname = persona.scratch.get_str_firstname() if hasattr(persona.scratch, "get_str_firstname") else persona.name
  topics = _MOTIVE_FOCAL_TOPICS.get(str(motive_key or "").strip().lower(), ())
  return [f"Recent {topic} experiences for {firstname}" for topic in topics]


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


def rerank_by_motive(retrieved, motive_key, n_count=8):
  scored = []
  keywords = _MOTIVE_MEMORY_KEYWORDS.get(motive_key, set())
  for rank, node in _flatten_unique_nodes(retrieved):
    memory_tags = getattr(node, "memory_tags", None) or {}
    haystack = " ".join([
      _normalize_text(getattr(node, "description", "")),
      _normalize_text(getattr(node, "subject", "")),
      _normalize_text(getattr(node, "predicate", "")),
      _normalize_text(getattr(node, "object", "")),
      " ".join(sorted(_normalize_text(keyword) for keyword in getattr(node, "keywords", set()))),
      _normalize_text(memory_tags.get("dominant_motive")),
    ])
    keyword_bonus = sum(2.5 for keyword in keywords if keyword in haystack)
    effects = getattr(node, "motive_effects", None) or getattr(node, "attribute_effects", None) or {}
    try:
      effect_bonus = abs(float(effects.get(motive_key, 0.0) or 0.0)) * 0.15
    except Exception:
      effect_bonus = 0.0
    score = keyword_bonus + effect_bonus + max(0.0, 2.0 - rank * 0.2)
    score += float(getattr(node, "poignancy", 0.0) or 0.0) * 0.05
    scored.append((score, node))
  scored.sort(key=lambda item: item[0], reverse=True)
  return [node for _score, node in scored[:n_count]]


def retrieve_memories_by_motives(persona, dominant_motive, secondary_motive=None, n_count_per_motive=8):
  """Independently retrieve dominant and secondary motive memories, then deduplicate."""
  if not getattr(persona, "a_mem", None):
    return {"dominant": [], "secondary": [], "combined": []}
  if not (persona.a_mem.seq_event or persona.a_mem.seq_thought):
    return {"dominant": [], "secondary": [], "combined": []}

  results = {}
  for role, motive in (("dominant", dominant_motive), ("secondary", secondary_motive)):
    if not motive or (role == "secondary" and motive == dominant_motive):
      results[role] = []
      continue
    focal_points = build_motive_focal_points(persona, motive)
    raw_retrieved = new_retrieve(persona, focal_points, n_count=max(n_count_per_motive, 12))
    results[role] = rerank_by_motive(raw_retrieved, motive, n_count=n_count_per_motive)

  combined = []
  seen = set()
  for node in results["dominant"] + results["secondary"]:
    identity = getattr(node, "node_id", None) or id(node)
    if identity in seen:
      continue
    seen.add(identity)
    combined.append(node)
  results["combined"] = combined
  append_debug_log(
    INTENT_MEMORY_LOG,
    merge_log_context(
      {
        "persona": getattr(persona, "name", None),
        "retrieval_mode": "dominant_secondary_motives",
        "dominant_motive": dominant_motive,
        "secondary_motive": secondary_motive,
        "dominant_memory_ids": [getattr(node, "node_id", None) for node in results["dominant"]],
        "secondary_memory_ids": [getattr(node, "node_id", None) for node in results["secondary"]],
      },
      persona=persona,
    ),
  )
  return results


def summarize_intent_memories(intent_family, retrieved_nodes, max_items=7, max_chars=550):
  if not intent_family or not retrieved_nodes:
    return ""

  label_map = {
    "restore_satiety": "food-related experience",
    "restore_stamina": "recovery-related experience",
    "restore_health": "health-related experience",
    "restore_mood": "mood-related experience",
  }
  label = label_map.get(intent_family, "relevant experience")
  success_lines = []
  failure_lines = []
  for node in retrieved_nodes:
    description = str(getattr(node, "description", "") or "").strip()
    if not description:
      continue
    attribute_effects = getattr(node, "attribute_effects", None) or {}
    primary_attr = {
      "restore_satiety": "satiety",
      "restore_stamina": "stamina",
      "restore_health": "health",
      "restore_mood": "mood",
    }.get(intent_family)
    primary_delta = float(attribute_effects.get(primary_attr, 0.0) or 0.0) if primary_attr else 0.0
    lowered = _normalize_text(description)
    is_failure = (
      primary_delta < 0.0
      or any(token in lowered for token in {"failed", "empty", "depleted", "unreachable", "path_not_found", "could not"})
    )
    if is_failure:
      failure_lines.append(f"- {description}")
    else:
      success_lines.append(f"- {description}")
  
  selected_success = success_lines[:4]
  selected_failure = failure_lines[:3]

  lines = [f"Relevant prior {label}:"]
  if selected_success:
    lines.append("Successful experience:")
    lines.extend(selected_success)
  if selected_failure:
    lines.append("Failed attempts:")
    lines.extend(selected_failure)

  summary = "\n".join(lines)
  if len(summary) > max_chars:
    summary = summary[:max_chars - 15].rstrip() + "...(truncated)"
  return summary


def summarize_memories_by_motives(retrieved_nodes, dominant_motive=None, secondary_motive=None, max_items=12):
  """Format retrieved memories by current motive relevance for the decision Prompt."""
  if not retrieved_nodes:
    return ""

  groups = {
    "dominant": {"success": [], "failure": []},
    "secondary": {"success": [], "failure": []},
    "other": {"success": [], "failure": []},
  }
  for node in retrieved_nodes[:max_items]:
    description = str(getattr(node, "description", "") or "").strip()
    if not description:
      continue
    attribute_effects = getattr(node, "attribute_effects", None) or {}
    text = _normalize_text(" ".join([
      description,
      str(getattr(node, "subject", "") or ""),
      str(getattr(node, "predicate", "") or ""),
      str(getattr(node, "object", "") or ""),
    ]))

    def is_relevant(motive):
      if not motive:
        return False
      if float(attribute_effects.get(motive, 0.0) or 0.0) != 0.0:
        return True
      return any(keyword in text for keyword in _MOTIVE_MEMORY_KEYWORDS.get(motive, set()))

    is_failure = (
      any(float(delta or 0.0) < 0.0 for delta in attribute_effects.values())
      or any(token in text for token in {"failed", "empty", "depleted", "unreachable", "path_not_found", "could not"})
    )
    group_key = "dominant" if is_relevant(dominant_motive) else "secondary" if is_relevant(secondary_motive) else "other"
    groups[group_key]["failure" if is_failure else "success"].append(description)

  name_lookup = dict(_MOTIVE_MEMORY_GROUPS)
  lines = ["相关记忆 / 经验（按当前动机分类）:"]
  def append_group(group_key, title):
    group = groups[group_key]
    if not group["success"] and not group["failure"]:
      return
    lines.append(title)
    if group["success"]:
      lines.append("成功经验:")
      lines.extend(f"⭐ {description}" for description in group["success"][:2])
    if group["failure"]:
      lines.append("失败尝试（避免重复）:")
      lines.extend(f"⚠ {description}" for description in group["failure"][:2])

  if groups["dominant"]["success"] or groups["dominant"]["failure"]:
    append_group("dominant", f"主导动机相关（{name_lookup.get(dominant_motive, dominant_motive)} / {dominant_motive}）:")
  if groups["secondary"]["success"] or groups["secondary"]["failure"]:
    append_group("secondary", f"次要动机相关（{name_lookup.get(secondary_motive, secondary_motive)} / {secondary_motive}）:")
  if groups["other"]["success"] or groups["other"]["failure"]:
    append_group("other", "其他可参考经验:")
  return "\n".join(lines) if len(lines) > 1 else ""


def retrieve_intent_memories(persona, intent_family, action_signature=None, n_count=10):
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
  raw_retrieved = new_retrieve(persona, focal_points, n_count=max(n_count, 12))
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
    merge_log_context(
      {
        "persona": getattr(persona, "name", None),
        "intent_family": intent_family,
        "focal_points": focal_points,
        "selected_memory_ids": [getattr(node, "node_id", None) for node in reranked],
        "selected_memory_descriptions": [getattr(node, "description", "") for node in reranked],
        "attribute_preferences": attribute_preferences,
        "summary_chars": len(summary),
        "duration_ms": round((time.perf_counter() - started_at) * 1000.0, 3),
      },
      persona=persona,
    )
  )
  return reranked
