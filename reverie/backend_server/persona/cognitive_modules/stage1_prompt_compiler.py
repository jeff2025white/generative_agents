"""
Stage 1 prompt profile and dynamic context compiler.

This module keeps persistent prompt-profile fields separate from the
per-decision prompt assembly logic used by demand thinking and joint decision.
"""

import os
from pathlib import Path

from persona.cognitive_modules.decision_constraints import build_invalid_targets
from persona.cognitive_modules.motive_selector import (
  build_default_motive_attributes,
  select_motives,
  sync_core_motive_values,
)
from persona.prompt_template.gpt_structure import ChatGPT_single_request, generate_prompt


DRIVE_SYSTEM_SUMMARY_TEXT = (
  "satiety=food seeking; stamina=rest and recovery; health=injury avoidance and healing; "
  "safety=risk avoidance; mood=emotion repair; belonging=social connection; "
  "status=recognition and standing; autonomy=self-direction; competence=mastery and effectiveness; "
  "meaning=purpose and significance."
)
WORLD_RULES_TEXT = (
  "Physical Rules: The world follows hard feasibility constraints. "
  "The agent can only choose one immediate action per step, and the target must be physically reachable now. "
  "If inventory has no edible item, Consume is invalid until food is first Gathered or received. "
  "Any target listed in InvalidTargets is forbidden for this step. "
  "If the previous action failed due to path_not_found or unreachable target, the same failed target must not be repeated immediately; "
  "a new feasible target or materially different immediate plan is required. "
  "If a resource was reached but empty, treat it as fresh evidence and switch to another feasible source. "
  "Prioritize survival and feasibility first: critical satiety/stamina/health needs override routine role behavior, "
  "while identity, lifestyle, and long-term goals only break ties among feasible immediate options."
)
LEGACY_PROMPT_PROFILE_SOURCES = {"legacy_bootstrap", "legacy_fallback"}
_PROMPT_TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "prompt_template" / "v2"
CURRENT_SITUATION_SUMMARY_TEMPLATE = str(_PROMPT_TEMPLATE_ROOT / "stage1_current_situation_summary_v1.txt")
LONG_TERM_GOALS_SUMMARY_TEMPLATE = str(_PROMPT_TEMPLATE_ROOT / "stage1_long_term_goals_summary_v1.txt")


def _compact_text(value):
  text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
  return " ".join(text.split())


def _trim_text(text, max_chars=420):
  text = _compact_text(text)
  if len(text) <= max_chars:
    return text
  return text[: max_chars - 3].rstrip() + "..."


def _safe_float(value, default=0.0):
  try:
    return float(value)
  except Exception:
    return default


def _truthy_env_flag(name, default=False):
  raw = os.environ.get(name)
  if raw is None:
    return default
  return str(raw).strip().lower() not in {"", "0", "false", "no", "off"}


def _format_curr_time(scratch):
  curr_time = getattr(scratch, "curr_time", None)
  if curr_time is None:
    return None
  try:
    if isinstance(curr_time, str):
      return curr_time
    return curr_time.strftime("%Y-%m-%d %H:%M:%S")
  except Exception:
    return str(curr_time)


def _get_motive_result(persona):
  scratch = getattr(persona, "scratch", None)
  if scratch is None:
    return {}
  getter = getattr(scratch, "get_motive_attributes_snapshot", None)
  if callable(getter):
    motive_attributes = getter()
  else:
    motive_attributes = sync_core_motive_values(
      build_default_motive_attributes(),
      satiety=getattr(scratch, "satiety", 100.0),
      stamina=getattr(scratch, "stamina", 100.0),
      health=getattr(scratch, "health", 100.0),
      mood=getattr(scratch, "mood", 100.0),
    )
  return select_motives(motive_attributes)


def build_drive_system_summary_text():
  return DRIVE_SYSTEM_SUMMARY_TEXT


def build_motive_guidance_text(persona):
  motive_result = _get_motive_result(persona)
  dominant = motive_result.get("dominant_motive") or "unknown"
  secondary = motive_result.get("secondary_motive")
  urgency_band = motive_result.get("dominant_urgency_band") or "unknown"
  dominant_strength = motive_result.get("dominant_strength") or "weak"
  has_urgent_motive = bool(motive_result.get("has_urgent_motive"))
  motive_sentence = _compact_text(motive_result.get("motive_sentence"))
  reasoning = _compact_text(motive_result.get("reasoning"))
  parts = [
    f"dominant={dominant}",
    f"urgency={urgency_band}",
  ]
  if secondary and has_urgent_motive:
    parts.append(f"secondary={secondary}")
  if not has_urgent_motive:
    parts.append("No urgent internal need dominates this step.")
  elif motive_sentence:
    parts.append(motive_sentence)
  if reasoning:
    parts.append(f"Reasoning: {reasoning}")
  if dominant_strength == "weak":
    parts.append("Dominant motive should only act as a light tie-breaker right now.")
  return " ".join(parts)


def build_world_rules_text(persona, base_rules=None):
  return WORLD_RULES_TEXT


def build_relevant_experience_text(intent_memory_summary=None):
  if intent_memory_summary:
    return _compact_text(intent_memory_summary)
  return "No especially relevant prior experience was retrieved."


def build_decision_social_context_text(persona, cooperative_context=None):
  scratch = getattr(persona, "scratch", None)
  social_summary = ""
  if scratch is not None:
    getter = getattr(scratch, "get_prompt_profile_field", None)
    if callable(getter):
      social_summary = getter("social_relationships_text")
  legacy_empty_values = {
    "",
    "No social relationship summary has been cached yet.",
    "暂无其他 NPC 信息缓存。",
    "暂无社交关系信息缓存。",
  }
  if social_summary in legacy_empty_values:
    social_summary = _build_social_relationships_profile_text(persona)
  social_summary = _compact_text(social_summary) or "暂无其他 NPC 信息缓存。"

  current_social = []
  chatting_with = getattr(scratch, "chatting_with", None) if scratch is not None else None
  if chatting_with and chatting_with != "<creator>":
    current_social.append(f"当前正在与 {chatting_with} 交流。")
  if cooperative_context and "No special" not in str(cooperative_context):
    current_social.append(_compact_text(cooperative_context))
  if current_social:
    social_summary = social_summary + " " + " ".join(current_social)
  return social_summary.strip()


def build_background_identity_text(persona):
  scratch = getattr(persona, "scratch", None)
  if scratch is None:
    return ""
  profile_getter = getattr(scratch, "get_prompt_profile", None)
  if callable(profile_getter):
    profile = profile_getter()
  else:
    profile = _build_fallback_prompt_profile(persona)
  fields = profile.get("fields") or {}

  def field_value(field_name, fallback=""):
    entry = fields.get(field_name) or {}
    value = _compact_text(entry.get("value"))
    return value or fallback

  lines = [
    f"Name: {getattr(scratch, 'name', None) or getattr(persona, 'name', None) or 'Unknown'}",
    f"Age: {getattr(scratch, 'age', 'Unknown')}",
    f"Innate Traits: {field_value('innate_traits_text', _compact_text(getattr(scratch, 'innate', None)) or 'Unknown')}",
    f"Learned Traits: {field_value('learned_traits_text', _compact_text(getattr(scratch, 'learned', None)) or 'Not summarized yet.')}",
    f"Long-Term Goals: {field_value('long_term_goals_text', 'First, stay alive and preserve basic wellbeing.')}",
    f"Current Situation: {field_value('current_situation_text', _compact_text(getattr(scratch, 'currently', None)) or 'No current situation summary cached yet.')}",
    f"Lifestyle: {field_value('lifestyle_text', _compact_text(getattr(scratch, 'lifestyle', None)) or 'No lifestyle summary cached yet.')}",
    f"Daily Plan: {field_value('daily_plan_text', _compact_text(getattr(scratch, 'daily_plan_req', None)) or 'No daily plan summary cached yet.')}",
    f"其他人: {_build_other_people_text(persona)}",
  ]
  return "\n".join(lines)


def _flatten_prompt_profile(profile):
  fields = {}
  for field_name, record in (profile.get("fields") or {}).items():
    record = record or {}
    fields[field_name] = {
      "value": _compact_text(record.get("value")),
      "source": record.get("source"),
      "updated_at": record.get("updated_at"),
      "version": record.get("version"),
    }
  return {
    "schema_version": profile.get("schema_version"),
    "last_compiled_at": profile.get("last_compiled_at"),
    "fields": fields,
  }


def _build_fallback_prompt_profile(persona):
  scratch = getattr(persona, "scratch", None)
  return {
    "schema_version": 1,
    "last_compiled_at": None,
    "fields": {
      "innate_traits_text": {"value": getattr(scratch, "innate", None), "source": "legacy_fallback"},
      "learned_traits_text": {"value": getattr(scratch, "learned", None), "source": "legacy_fallback"},
      "current_situation_text": {"value": getattr(scratch, "currently", None), "source": "legacy_fallback"},
      "long_term_goals_text": {"value": "First, stay alive and preserve basic wellbeing.", "source": "legacy_fallback"},
      "lifestyle_text": {"value": getattr(scratch, "lifestyle", None), "source": "legacy_fallback"},
      "daily_plan_text": {"value": getattr(scratch, "daily_plan_req", None), "source": "legacy_fallback"},
      "social_relationships_text": {"value": getattr(scratch, "chatting_with", None), "source": "legacy_fallback"},
    },
  }


def _get_profile_record(scratch, field_name):
  profile_getter = getattr(scratch, "get_prompt_profile", None)
  if not callable(profile_getter):
    return {}
  profile = profile_getter()
  return (profile.get("fields") or {}).get(field_name) or {}


def _is_legacy_or_empty_record(record):
  source = str((record or {}).get("source") or "")
  value = _compact_text((record or {}).get("value"))
  return (not value) or source in LEGACY_PROMPT_PROFILE_SOURCES


def _set_prompt_profile_field(scratch, field_name, value, source, *, overwrite=True):
  setter = getattr(scratch, "set_prompt_profile_field", None)
  getter = getattr(scratch, "get_prompt_profile", None)
  if not callable(setter) or not callable(getter):
    return False
  record = _get_profile_record(scratch, field_name)
  if not overwrite and not _is_legacy_or_empty_record(record):
    return False
  setter(field_name, value, source=source)
  return True


def _build_daily_plan_profile_text(scratch):
  daily_plan_req = _compact_text(getattr(scratch, "daily_plan_req", None))
  if daily_plan_req:
    return daily_plan_req
  daily_req = getattr(scratch, "daily_req", None) or []
  if isinstance(daily_req, (list, tuple)):
    entries = [_compact_text(item) for item in daily_req if _compact_text(item)]
    if entries:
      return "; ".join(entries[:6])
  return "No daily plan summary has been cached yet."


def _coerce_persona_mapping(personas):
  if isinstance(personas, dict):
    return personas
  if isinstance(personas, (list, tuple)):
    mapped = {}
    for candidate in personas:
      name = getattr(candidate, "name", None)
      if name:
        mapped[str(name)] = candidate
    return mapped
  return {}


def _lookup_runtime_persona(observer_persona, target_name):
  for attr_name in ("runtime_known_personas", "known_personas", "all_personas", "personas"):
    mapped = _coerce_persona_mapping(getattr(observer_persona, attr_name, None))
    if target_name in mapped:
      return mapped[target_name]
  return None


def _extract_innate_traits_text(target_persona):
  if target_persona is None:
    return ""
  scratch = getattr(target_persona, "scratch", None)
  if scratch is None:
    return ""
  getter = getattr(scratch, "get_prompt_profile_field", None)
  if callable(getter):
    innate = getter("innate_traits_text")
    if innate:
      return _compact_text(innate)
  return _compact_text(getattr(scratch, "innate", None))


def _extract_learned_traits_text(target_persona):
  if target_persona is None:
    return ""
  scratch = getattr(target_persona, "scratch", None)
  if scratch is None:
    return ""
  getter = getattr(scratch, "get_prompt_profile_field", None)
  if callable(getter):
    learned = getter("learned_traits_text")
    if learned:
      return _compact_text(learned)
  return _compact_text(getattr(scratch, "learned", None))


def remember_known_persona_profile(observer_persona, target_persona, source="runtime_observation"):
  if observer_persona is None or target_persona is None:
    return False
  observer_scratch = getattr(observer_persona, "scratch", None)
  target_scratch = getattr(target_persona, "scratch", None)
  if observer_scratch is None or target_scratch is None:
    return False
  target_name = getattr(target_persona, "name", None) or getattr(target_scratch, "name", None)
  if not target_name:
    return False
  knowledge = getattr(observer_scratch, "personal_knowledge", None)
  if not isinstance(knowledge, dict):
    observer_scratch.personal_knowledge = {}
    knowledge = observer_scratch.personal_knowledge
  profiles = knowledge.setdefault("persona_profiles", {})
  profiles[str(target_name)] = {
    "name": str(target_name),
    "innate_traits_text": _extract_innate_traits_text(target_persona),
    "learned_traits_text": _extract_learned_traits_text(target_persona),
    "source": str(source or "runtime_observation"),
  }
  return True


def _lookup_persona_profile_knowledge(observer_persona, target_name):
  scratch = getattr(observer_persona, "scratch", None)
  if scratch is None:
    return {}
  personal_knowledge = getattr(scratch, "personal_knowledge", None)
  if not isinstance(personal_knowledge, dict):
    return {}
  profiles = personal_knowledge.get("persona_profiles", {})
  if isinstance(profiles, dict):
    profile = profiles.get(target_name)
    if isinstance(profile, dict):
      return profile
  direct = personal_knowledge.get(target_name)
  if isinstance(direct, dict):
    return direct
  return {}


def _iter_reflection_thoughts(persona, limit=16, min_poignancy=3.0):
  a_mem = getattr(persona, "a_mem", None)
  seq_thought = getattr(a_mem, "seq_thought", None) or []
  scratch = getattr(persona, "scratch", None)
  curr_time = getattr(scratch, "curr_time", None) if scratch is not None else None
  scored_nodes = []
  for node in seq_thought:
    description = _compact_text(getattr(node, "description", None) or getattr(node, "embedding_key", None))
    if not description:
      continue
    poignancy = _safe_float(getattr(node, "poignancy", 0.0), default=0.0)
    if poignancy < min_poignancy:
      continue
    created = getattr(node, "created", None)
    recency_bonus = 0.0
    if curr_time is not None and created is not None:
      try:
        delta_seconds = max(0.0, (curr_time - created).total_seconds())
        recency_bonus = max(0.0, 3.0 - min(3.0, delta_seconds / 86400.0))
      except Exception:
        recency_bonus = 0.0
    depth_bonus = min(1.5, _safe_float(getattr(node, "depth", 0.0), default=0.0) * 0.2)
    filling = getattr(node, "filling", None) or []
    evidence_bonus = min(1.0, len(filling) * 0.1) if isinstance(filling, (list, tuple, set)) else 0.0
    score = poignancy + recency_bonus + depth_bonus + evidence_bonus
    scored_nodes.append((score, node, description))
  scored_nodes.sort(
    key=lambda item: (
      -item[0],
      str(getattr(item[1], "created", "") or ""),
      item[2].lower(),
    )
  )
  return scored_nodes[:limit]


def _thought_text_mentions_social(text):
  lowered = str(text or "").lower()
  keywords = (
    "conversation",
    "talk",
    "chat",
    "friend",
    "relationship",
    "trust",
    "help",
    "together",
    "klaus",
    "maria",
    "isabella",
  )
  return any(keyword in lowered for keyword in keywords)


def _select_current_situation_reflections(persona, limit=3):
  selected = []
  for _score, node, description in _iter_reflection_thoughts(persona, limit=12, min_poignancy=3.0):
    lowered = description.lower()
    is_planning = (
      "planning" in lowered
      or "plan" in lowered
      or "preparing" in lowered
      or "working on" in lowered
      or "need to" in lowered
      or "should " in lowered
    )
    if is_planning or _thought_text_mentions_social(lowered):
      selected.append(description)
    if len(selected) >= limit:
      break
  return selected


def _extract_goal_themes(persona, limit=4):
  theme_counts = {}
  for _score, node, description in _iter_reflection_thoughts(persona, limit=18, min_poignancy=4.0):
    keywords = getattr(node, "keywords", None) or []
    lowered_description = description.lower()
    normalized_keywords = [str(keyword).strip().lower() for keyword in keywords]
    for keyword in normalized_keywords:
      if keyword in {"plan", "think", "thought", "idle", "chat"}:
        continue
      if len(keyword) < 4:
        continue
      theme_counts[keyword] = theme_counts.get(keyword, 0) + 1.0
    theme_hints = (
      ("survive", ("survive", "alive", "health", "food", "hungry", "safety")),
      ("relationships", ("friend", "relationship", "trust", "chat", "together", "help")),
      ("work", ("work", "job", "cafe", "serve", "duty", "counter")),
      ("research", ("research", "paper", "library", "study", "learn")),
      ("routine", ("routine", "daily", "rest", "sleep", "steady")),
    )
    for label, hints in theme_hints:
      if any(hint in lowered_description for hint in hints):
        theme_counts[label] = theme_counts.get(label, 0) + 1.5
  ordered = sorted(theme_counts.items(), key=lambda item: (-item[1], item[0]))
  return [name for name, _score in ordered[:limit]]


def _build_reflection_candidate_lines(persona, limit=6, min_poignancy=4.0):
  lines = []
  for score, node, description in _iter_reflection_thoughts(persona, limit=limit, min_poignancy=min_poignancy):
    created = getattr(node, "created", None)
    created_text = ""
    if created is not None:
      try:
        created_text = created.strftime("%Y-%m-%d %H:%M")
      except Exception:
        created_text = str(created)
    keywords = ", ".join(sorted(str(keyword).strip().lower() for keyword in (getattr(node, "keywords", None) or []) if str(keyword).strip()))
    line = f"- poignancy={_safe_float(getattr(node, 'poignancy', 0.0), 0.0):.1f}"
    if created_text:
      line += f"; created={created_text}"
    if keywords:
      line += f"; keywords={keywords}"
    line += f"; thought={description}"
    lines.append(line)
  return "\n".join(lines) if lines else "- No high-value reflection thoughts were available."


def _should_try_llm_profile_summary(persona, candidates, *, force_llm=False):
  if force_llm:
    return True
  if len(candidates) < 2:
    return False
  if getattr(persona, "disable_llm_profile_summaries", False):
    return False
  if getattr(persona, "enable_llm_profile_summaries", False):
    return True
  if _truthy_env_flag("ENABLE_STAGE1_PROFILE_LLM_SUMMARIES", default=False):
    return True
  a_mem = getattr(persona, "a_mem", None)
  return bool(getattr(a_mem, "id_to_node", None))


def _clean_summary_response(response):
  text = _compact_text(response)
  if not text:
    return ""
  if text.startswith('"') and text.endswith('"'):
    text = text[1:-1].strip()
  return text


def _llm_profile_summary(persona,
                         *,
                         candidates,
                         template_path,
                         prompt_inputs,
                         fallback_text,
                         max_chars,
                         force_llm=False):
  if not _should_try_llm_profile_summary(persona, candidates, force_llm=force_llm):
    return _trim_text(fallback_text, max_chars=max_chars)
  try:
    prompt = generate_prompt(prompt_inputs, template_path)
    response = ChatGPT_single_request(prompt)
    cleaned = _clean_summary_response(response)
    if not cleaned:
      return _trim_text(fallback_text, max_chars=max_chars)
    return _trim_text(cleaned, max_chars=max_chars)
  except Exception:
    return _trim_text(fallback_text, max_chars=max_chars)


def summarize_current_situation_from_reflection(persona):
  scratch = getattr(persona, "scratch", None)
  base_currently = _compact_text(getattr(scratch, "currently", None))
  reflections = _select_current_situation_reflections(persona, limit=3)
  fallback_text = base_currently or "No current situation summary cached yet."
  if not reflections:
    return _trim_text(fallback_text, max_chars=360)
  parts = []
  if base_currently:
    parts.append(base_currently)
  parts.append("Recent reflection signals:")
  parts.extend(reflections)
  heuristic_summary = _trim_text(" ".join(parts), max_chars=360)
  reflection_candidates = _build_reflection_candidate_lines(persona, limit=6, min_poignancy=4.0)
  prompt_inputs = [
    getattr(getattr(persona, "scratch", None), "name", None) or getattr(persona, "name", None) or "Unknown",
    base_currently or "No existing current situation text.",
    _build_daily_plan_profile_text(scratch),
    reflection_candidates,
  ]
  return _llm_profile_summary(
    persona,
    candidates=reflections,
    template_path=CURRENT_SITUATION_SUMMARY_TEMPLATE,
    prompt_inputs=prompt_inputs,
    fallback_text=heuristic_summary,
    max_chars=360,
  )


def summarize_long_term_goals_from_reflection(persona):
  scratch = getattr(persona, "scratch", None)
  lifestyle = _compact_text(getattr(scratch, "lifestyle", None))
  learned = _compact_text(getattr(scratch, "learned", None))
  theme_names = _extract_goal_themes(persona, limit=4)

  text = (
    "First, stay alive and preserve my basic wellbeing in this sandbox world. "
    "I need reliable food, rest, and safety so I do not fall into an unrecoverable state."
  )
  theme_sentences = []
  if "relationships" in theme_names:
    theme_sentences.append(
      "Beyond survival, I want to maintain dependable relationships and use them to create a steadier life."
    )
  if "work" in theme_names:
    theme_sentences.append(
      "I also want to keep fulfilling my practical responsibilities and stay useful in my usual role."
    )
  if "research" in theme_names:
    theme_sentences.append(
      "I want to keep making progress on the intellectual work and study that define my direction."
    )
  if "routine" in theme_names:
    theme_sentences.append(
      "A stable routine matters because it helps me stay functional while pursuing longer plans."
    )
  if not theme_sentences and learned:
    theme_sentences.append(f"I want to keep building on my developed strengths: {learned}.")
  if lifestyle and "routine" not in theme_names:
    theme_sentences.append(f"My preferred rhythm is: {lifestyle}.")
  if not theme_sentences:
    theme_sentences.append(
      "After securing survival, I want to keep following the routines, relationships, and responsibilities that fit who I am."
    )
  text = text + " " + " ".join(theme_sentences[:3])
  heuristic_summary = _trim_text(text, max_chars=420)
  reflection_candidates = _build_reflection_candidate_lines(persona, limit=8, min_poignancy=4.0)
  llm_candidates = [description for _score, _node, description in _iter_reflection_thoughts(persona, limit=8, min_poignancy=4.0)]
  prompt_inputs = [
    getattr(getattr(persona, "scratch", None), "name", None) or getattr(persona, "name", None) or "Unknown",
    learned or "No learned-traits summary available.",
    lifestyle or "No lifestyle summary available.",
    ", ".join(theme_names) if theme_names else "survival, routine",
    reflection_candidates,
  ]
  return _llm_profile_summary(
    persona,
    candidates=llm_candidates,
    template_path=LONG_TERM_GOALS_SUMMARY_TEMPLATE,
    prompt_inputs=prompt_inputs,
    fallback_text=heuristic_summary,
    max_chars=420,
  )


def _get_target_static_profile(observer_persona, target_name):
  runtime_persona = _lookup_runtime_persona(observer_persona, target_name)
  if runtime_persona is not None:
    remember_known_persona_profile(observer_persona, runtime_persona, source="runtime_known_personas")
    return {
      "innate_traits_text": _extract_innate_traits_text(runtime_persona),
      "learned_traits_text": _extract_learned_traits_text(runtime_persona),
    }
  knowledge_profile = _lookup_persona_profile_knowledge(observer_persona, target_name)
  return {
    "innate_traits_text": _compact_text(knowledge_profile.get("innate_traits_text")),
    "learned_traits_text": _compact_text(knowledge_profile.get("learned_traits_text")),
  }


def _iter_other_persona_profiles(observer_persona):
  observer_name = str(getattr(observer_persona, "name", "") or "").strip()
  emitted = set()

  for attr_name in ("runtime_known_personas", "known_personas", "all_personas", "personas"):
    mapped = _coerce_persona_mapping(getattr(observer_persona, attr_name, None))
    for target_name, runtime_persona in sorted(mapped.items(), key=lambda item: str(item[0]).lower()):
      normalized_name = str(target_name or "").strip()
      if not normalized_name or normalized_name in emitted or normalized_name == observer_name:
        continue
      if normalized_name == "<creator>":
        continue
      emitted.add(normalized_name)
      remember_known_persona_profile(observer_persona, runtime_persona, source=f"runtime:{attr_name}")
      yield {
        "name": normalized_name,
        "innate_traits_text": _extract_innate_traits_text(runtime_persona),
      }

  scratch = getattr(observer_persona, "scratch", None)
  personal_knowledge = getattr(scratch, "personal_knowledge", None) if scratch is not None else None
  profiles = {}
  if isinstance(personal_knowledge, dict):
    profiles = personal_knowledge.get("persona_profiles", {})
  if isinstance(profiles, dict):
    for target_name, profile in sorted(profiles.items(), key=lambda item: str(item[0]).lower()):
      normalized_name = str(target_name or "").strip()
      if not normalized_name or normalized_name in emitted or normalized_name == observer_name:
        continue
      if normalized_name == "<creator>":
        continue
      emitted.add(normalized_name)
      profile = profile or {}
      yield {
        "name": normalized_name,
        "innate_traits_text": _compact_text(profile.get("innate_traits_text")),
      }


def _build_other_people_text(observer_persona, max_people=6):
  entries = []
  for profile in _iter_other_persona_profiles(observer_persona):
    name = _compact_text(profile.get("name"))
    if not name:
      continue
    innate_traits = _compact_text(profile.get("innate_traits_text")) or "未知"
    entries.append(f"{name}: 天生特质={innate_traits}")
    if len(entries) >= max_people:
      break
  if not entries:
    return "暂无其他 NPC 信息缓存。"
  return "； ".join(entries)


def _build_social_relationships_profile_text(persona, memo_thought=None):
  scratch = getattr(persona, "scratch", None)
  a_mem = getattr(persona, "a_mem", None)
  graph = getattr(a_mem, "social_relationship_graph", {}) or {}
  relations = (graph.get("relations") or {}) if isinstance(graph, dict) else {}
  relation_items = []
  for target_name, payload in relations.items():
    payload = payload or {}
    trust = payload.get("trust", 0.0)
    try:
      trust_value = float(trust)
    except Exception:
      trust_value = 0.0
    relation_items.append((trust_value, str(target_name), payload))
  relation_items.sort(key=lambda item: (-item[0], item[1].lower()))

  summary_parts = []
  chatting_with = getattr(scratch, "chatting_with", None) if scratch is not None else None
  if chatting_with and chatting_with != "<creator>":
    target_profile = _get_target_static_profile(persona, chatting_with)
    chatting_traits = _compact_text(target_profile.get("innate_traits_text"))
    partner_line = f"当前正在交流对象: {chatting_with}。"
    if chatting_traits:
      partner_line += f" 对方天生特质: {chatting_traits}。"
    summary_parts.append(partner_line)

  for trust_value, target_name, payload in relation_items[:3]:
    _get_target_static_profile(persona, target_name)
    relation = _compact_text(payload.get("relationship")) or "unknown relation"
    recent_events = payload.get("recent_events") or []
    recent_event = _compact_text(recent_events[-1]) if recent_events else ""
    part = f"{target_name}: 亲密程度={trust_value:.2f}"
    if relation:
      part += f", 关系={relation}"
    if recent_event:
      part += f", 最近互动={recent_event}"
    summary_parts.append(part)

  if memo_thought:
    summary_parts.append(f"最近社交反思: {_trim_text(memo_thought, max_chars=180)}")

  if not summary_parts:
    return "暂无社交关系信息缓存。"
  return " ".join(summary_parts)


def _build_long_term_goals_text(persona):
  return summarize_long_term_goals_from_reflection(persona)


def refresh_prompt_profile_basics(persona, source="state_sync"):
  scratch = getattr(persona, "scratch", None)
  if scratch is None:
    return False
  changed = False
  changed = _set_prompt_profile_field(
    scratch,
    "innate_traits_text",
    _compact_text(getattr(scratch, "innate", None)),
    source,
    overwrite=True,
  ) or changed
  changed = _set_prompt_profile_field(
    scratch,
    "learned_traits_text",
    _compact_text(getattr(scratch, "learned", None)),
    source,
    overwrite=True,
  ) or changed
  changed = _set_prompt_profile_field(
    scratch,
    "lifestyle_text",
    _compact_text(getattr(scratch, "lifestyle", None)),
    source,
    overwrite=True,
  ) or changed
  changed = _set_prompt_profile_field(
    scratch,
    "long_term_goals_text",
    _build_long_term_goals_text(persona),
    source,
    overwrite=True,
  ) or changed
  return changed


def refresh_prompt_profile_from_planning(persona, source="daily_planning"):
  scratch = getattr(persona, "scratch", None)
  if scratch is None:
    return False
  changed = refresh_prompt_profile_basics(persona, source=source)
  changed = _set_prompt_profile_field(
    scratch,
    "current_situation_text",
    summarize_current_situation_from_reflection(persona),
    source,
    overwrite=True,
  ) or changed
  changed = _set_prompt_profile_field(
    scratch,
    "daily_plan_text",
    _build_daily_plan_profile_text(scratch),
    source,
    overwrite=True,
  ) or changed
  changed = _set_prompt_profile_field(
    scratch,
    "social_relationships_text",
    _build_social_relationships_profile_text(persona),
    source,
    overwrite=True,
  ) or changed
  return changed


def refresh_prompt_profile_from_reflection(persona, planning_thought=None, memo_thought=None, source="reflection"):
  scratch = getattr(persona, "scratch", None)
  if scratch is None:
    return False
  changed = refresh_prompt_profile_basics(persona, source=source)

  planning_note = _compact_text(planning_thought)
  if planning_note:
    current_text = summarize_current_situation_from_reflection(persona)
    merged_text = current_text
    if planning_note not in current_text:
      merged_text = f"{current_text} Recent planning reflection: {planning_note}".strip()
    changed = _set_prompt_profile_field(
      scratch,
      "current_situation_text",
      _trim_text(merged_text, max_chars=360),
      source,
      overwrite=True,
    ) or changed

  social_text = _build_social_relationships_profile_text(persona, memo_thought=memo_thought)
  changed = _set_prompt_profile_field(
    scratch,
    "social_relationships_text",
    _trim_text(social_text, max_chars=360),
    source,
    overwrite=True,
  ) or changed
  changed = _set_prompt_profile_field(
    scratch,
    "long_term_goals_text",
    summarize_long_term_goals_from_reflection(persona),
    source,
    overwrite=True,
  ) or changed
  return changed


def compile_stage1_prompt_context(persona,
                                  *,
                                  base_rules=None,
                                  cooperative_context=None,
                                  intent_memory_summary=None):
  scratch = getattr(persona, "scratch", None)
  if scratch is None:
    return {
      "background_identity_text": "",
      "dynamic_fields": {},
      "prompt_profile": {},
      "trace_payload": {},
    }

  refresh_prompt_profile_basics(persona, source="decision_compile")
  profile_getter = getattr(scratch, "get_prompt_profile", None)
  if callable(profile_getter):
    prompt_profile = profile_getter()
  else:
    prompt_profile = _build_fallback_prompt_profile(persona)
  compiled_at = _format_curr_time(scratch)
  if compiled_at:
    prompt_profile["last_compiled_at"] = compiled_at
    if hasattr(scratch, "prompt_profile"):
      scratch.prompt_profile = prompt_profile

  dynamic_fields = {
    "world_rules_text": build_world_rules_text(persona, base_rules=base_rules),
    "drive_system_summary_text": build_drive_system_summary_text(),
    "motive_guidance_text": build_motive_guidance_text(persona),
    "relevant_experience_text": build_relevant_experience_text(intent_memory_summary),
    "decision_social_context_text": build_decision_social_context_text(
      persona,
      cooperative_context=cooperative_context,
    ),
  }
  background_identity_text = build_background_identity_text(persona)
  prompt_profile_snapshot = _flatten_prompt_profile(prompt_profile)

  return {
    "background_identity_text": background_identity_text,
    "dynamic_fields": dynamic_fields,
    "prompt_profile": prompt_profile_snapshot,
    "trace_payload": {
      "stage1_prompt_profile": prompt_profile_snapshot,
      "stage1_dynamic_fields": dynamic_fields,
    },
  }
