"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: plan.py
Description: This defines the "Plan" module for generative agents. 
"""
import datetime
import math
import os
import random 
import sys
import time
import uuid
sys.path.append('../../')

from global_methods import *
from llm_api_config import get_default_decision_request_config
from persona.cognitive_modules.action_command_utils import build_action_command, normalize_skill_id
from persona.cognitive_modules.action_target_resolver import (
  PLACE_TARGET_CANDIDATES,
  RESTABLE_OBJECT_TARGETS,
  resolve_action_target,
  resolve_candidate_object_address,
  resolve_candidate_place_address,
  resolve_persona_target,
  resolve_action_target_address,
)
from persona.cognitive_modules.debug_log import append_debug_log, safe_json_dumps
from persona.cognitive_modules.decision_constraints import (
  build_invalid_targets,
  build_retry_feedback,
  filter_invalid_resources,
  validate_decision_target,
)
from persona.cognitive_modules.decision_state_cache import (
  build_state_signature,
  get_cached_decision,
  put_cached_decision,
)
from persona.cognitive_modules.food_sources import (
  VALID_GATHER_FOOD_SOURCES,
  is_valid_gather_food_source,
  normalize_food_source_target,
)
from persona.cognitive_modules.intent_memory import (
  infer_memory_focus,
  retrieve_intent_memories,
  summarize_intent_memories,
)
from persona.cognitive_modules.motive_selector import (
  select_motives,
)
from persona.cognitive_modules.stage1_prompt_compiler import (
  refresh_prompt_profile_from_planning,
)
from persona.training.training_candidate_builder import normalize_training_log_record
from persona.cognitive_modules.social_trigger import (
  choose_social_focus,
  compute_social_cooldown,
  compute_social_opportunity_score,
  log_social_decision,
  minimum_social_chat_score,
  should_auto_initiate_social_chat,
  social_hard_block,
)
from persona.cognitive_modules.social_dialogue_log import (
  build_dialogue_id,
  clear_social_dialogue_state,
  log_social_dialogue,
  set_social_dialogue_state,
)
from persona.prompt_template.run_gpt_prompt import *
from persona.cognitive_modules.retrieve import *
from persona.cognitive_modules.converse import *

##############################################################################
# CHAPTER 2: Generate
##############################################################################

STEP_TIMING_LOG = "step_timing.jsonl"
DECISION_PROMPT_TRACE_LOG = "decision_prompt_trace.jsonl"
SLOW_TIMING_THRESHOLD_MS = 10000
_ACT_OBJ_STATE_CACHE = {}
COLLECTIVE_SOCIAL_TARGET_KEYWORDS = {
  "customer",
  "customers",
  "patron",
  "patrons",
  "people",
  "crowd",
  "guests",
  "visitors",
  "everyone",
  "others",
}

SOCIAL_VENUE_HINTS = (
  "pub",
  "bar",
  "tavern",
  "rose and crown",
)
STATIC_RESOURCE_PURPOSES = {
  "apple tree": "可获取食物",
  "refrigerator": "可获取 / 储存食物",
  "stove": "可准备食物 / 做饭",
  "cafe counter": "潜在食物来源 / 工作点位",
  "behind the cafe counter": "潜在食物来源 / 工作点位",
  "behind the bar counter": "社交服务 / 工作点位",
  "behind the grocery counter": "购物服务 / 工作点位",
  "behind the pharmacy counter": "购物服务 / 工作点位",
  "behind the supply store counter": "购物服务 / 工作点位",
  "bed": "休息 / 恢复体力",
  "sofa": "休息 / 恢复体力",
  "common room sofa": "休息 / 放松",
  "library sofa": "休息 / 阅读",
  "chair": "短暂休息 / 等待",
  "garden chair": "短暂休息 / 放松",
  "bench": "短暂休息 / 情绪修复",
  "park bench": "短暂休息 / 情绪修复",
  "desk": "工作 / 学习",
  "computer desk": "工作 / 学习",
  "computer": "工作 / 学习",
  "library table": "工作 / 学习",
  "bookshelf": "学习",
  "blackboard": "工作 / 教学",
  "classroom student seating": "学习 / 听课",
  "classroom podium": "教学 / 演讲",
  "game console": "娱乐 / 情绪修复",
  "piano": "娱乐 / 情绪修复",
  "pool table": "娱乐 / 社交",
  "park garden": "散步 / 情绪修复",
  "dorm garden": "散步 / 放松",
  "house garden": "散步 / 放松",
  "cafe customer seating": "社交 / 休息",
  "bar customer seating": "社交 / 休息",
  "common room": "社交 / 休息 / 放松",
  "library": "学习 / 工作",
  "plaza": "散步 / 社交",
  "courtyard": "散步 / 社交",
  "pub": "社交 / 情绪修复",
  "bar": "社交 / 情绪修复",
  "tavern": "社交 / 情绪修复",
  "rose and crown": "社交 / 情绪修复",
}


def _elapsed_ms(started_at):
  return round((time.perf_counter() - started_at) * 1000.0, 3)


def _address_has_approach_tile(maze, address):
  tiles = list(getattr(maze, "address_tiles", {}).get(address, []))
  if not tiles:
    return False
  for raw_tile in tiles:
    x, y = int(raw_tile[0]), int(raw_tile[1])
    tile_info = maze.access_tile((x, y))
    if tile_info and not tile_info.get("collision"):
      return True
    for neighbor in ((x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)):
      try:
        neighbor_info = maze.access_tile(neighbor)
      except Exception:
        neighbor_info = None
      if neighbor_info and not neighbor_info.get("collision"):
        return True
  return False


def _resource_purpose_for_label(label):
  normalized_label = str(label or "").strip().lower()
  return STATIC_RESOURCE_PURPOSES.get(normalized_label)


def _build_static_resource_context_text(persona, maze):
  scratch = getattr(persona, "scratch", None)
  maze_name = getattr(maze, "maze_name", None) or "default"
  cached_text = getattr(scratch, "static_resource_context_text", None) if scratch is not None else None
  cached_maze_name = getattr(scratch, "static_resource_context_maze_name", None) if scratch is not None else None
  if cached_text and cached_maze_name == maze_name:
    return cached_text

  entries = {}
  for address in sorted(getattr(maze, "address_tiles", {}).keys()):
    if str(address).startswith("<spawn_loc>"):
      continue
    parts = str(address).split(":")
    if len(parts) < 3:
      continue
    label = parts[-1].strip().lower()
    purpose = _resource_purpose_for_label(label)
    if not purpose:
      continue
    if not _address_has_approach_tile(maze, address):
      continue
    entries[label] = purpose

  if not entries:
    text = "可达的资源/场所:\n  暂无稳定关键资源记录"
  else:
    lines = ["可达的资源/场所:"]
    for label in sorted(entries):
      lines.append(f"  {label}:")
      lines.append(f"    用途: {entries[label]}")
    text = "\n".join(lines)

  if scratch is not None:
    scratch.static_resource_context_text = text
    scratch.static_resource_context_maze_name = maze_name
  return text


def _is_collective_social_target(target, detail=None):
  normalized = " ".join(
    str(value or "").strip().lower()
    for value in (target, detail)
    if value
  ).strip()
  if not normalized:
    return False
  tokens = set(normalized.replace("-", " ").split())
  return bool(tokens & COLLECTIVE_SOCIAL_TARGET_KEYWORDS)


def _extract_social_venue_target(target, detail):
  combined = " ".join(
    str(value or "").strip().lower()
    for value in (target, detail)
    if value
  )
  for hint in SOCIAL_VENUE_HINTS:
    if hint in combined:
      return hint
  return None


def _coerce_collective_social_hangout(action, target, act_desp, reasoning):
  normalized_skill_id = normalize_skill_id(action, target=target, detail=act_desp)
  if normalized_skill_id != "chat with" or not _is_collective_social_target(target, act_desp):
    return action, target, act_desp, reasoning, False
  venue_target = _extract_social_venue_target(target, act_desp)
  if not venue_target:
    return action, target, act_desp, reasoning, False
  hangout_description = (
    f"relaxing and people-watching at {venue_target}"
    if not act_desp
    else f"relaxing and people-watching at {venue_target}"
  )
  next_reasoning = str(reasoning or "")
  if next_reasoning:
    next_reasoning = f"{next_reasoning} [collective social target routed to venue hangout]"
  else:
    next_reasoning = "[collective social target routed to venue hangout]"
  return "hangout_social_venue", venue_target, hangout_description, next_reasoning, True


def _coerce_explicit_persona_chat(action, target, act_desp, reasoning, personas=None):
  normalized_skill_id = normalize_skill_id(action, target=target, detail=act_desp)
  if normalized_skill_id != "chat with":
    return action, target, act_desp, reasoning, False
  if _is_collective_social_target(target, act_desp):
    return action, target, act_desp, reasoning, False
  persona_resolution = resolve_persona_target(personas or {}, target)
  if not persona_resolution.get("ok"):
    return action, target, act_desp, reasoning, False
  next_reasoning = str(reasoning or "")
  if next_reasoning:
    next_reasoning = f"{next_reasoning} [explicit persona social intent routed to seek_and_chat]"
  else:
    next_reasoning = "[explicit persona social intent routed to seek_and_chat]"
  return "seek_and_chat", target, act_desp, next_reasoning, True


def _log_timing_event(event_name, payload):
  record = dict(payload or {})
  timings = record.get("timings_ms", {}) or {}
  max_stage_ms = 0.0
  try:
    max_stage_ms = max(float(v) for v in timings.values()) if timings else 0.0
  except Exception:
    max_stage_ms = 0.0
  total_ms = float(record.get("total_ms", max_stage_ms) or 0.0)
  record["event"] = event_name
  record["slow"] = bool(total_ms >= SLOW_TIMING_THRESHOLD_MS or max_stage_ms >= SLOW_TIMING_THRESHOLD_MS)
  append_debug_log(STEP_TIMING_LOG, record)


def _append_step_decision_trace(persona,
                                decision_id,
                                thinking_text,
                                reasoning,
                                decision,
                                action,
                                target,
                                act_desp,
                                motive_debug,
                                minimal_filter_summary,
                                collective_social_reroute=False,
                                explicit_persona_chat_reroute=False):
  curr_time = getattr(persona.scratch, "curr_time", None)
  if curr_time is None:
    sim_time = None
  else:
    try:
      sim_time = curr_time if isinstance(curr_time, str) else curr_time.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
      sim_time = str(curr_time)
  append_debug_log(
    DECISION_PROMPT_TRACE_LOG,
    {
      "event": "final_decision",
      "stage": "final_decision",
      "stage_order": 30,
      "decision_id": decision_id,
      "persona": persona.name,
      "curr_step": getattr(persona.scratch, "curr_step", None),
      "sim_time": sim_time,
      "llm_decision_text": {
        "thought": thinking_text,
        "reasoning": reasoning,
      },
      "decision": decision,
      "decision_routed_action": action,
      "decision_routed_target": target,
      "decision_routed_detail": act_desp,
      "decision_routed_reasoning": reasoning,
      "collective_social_reroute": bool(collective_social_reroute),
      "explicit_persona_chat_reroute": bool(explicit_persona_chat_reroute),
      "motives": motive_debug,
      "stats": {
        "satiety": persona.scratch.satiety,
        "stamina": persona.scratch.stamina,
        "health": persona.scratch.health,
        "mood": persona.scratch.mood,
      },
      "inventory": persona.scratch.inventory,
      "minimal_filter_enabled": bool((minimal_filter_summary or {}).get("enabled")),
      "minimal_filter_applied": bool((minimal_filter_summary or {}).get("applied")),
      "minimal_filter_summary": minimal_filter_summary or {},
    },
  )


def _build_action_record(persona, skill_id, target, act_desp, act_dura, resolved_address, reasoning, resolution_meta=None, creator_instruction=None):
  resolution_meta = resolution_meta or {}
  return {
    "status": "resolved",
    "skill_id": skill_id,
    "target": target,
    "target_type": resolution_meta.get("target_type"),
    "resolved_target": resolution_meta.get("matched") or target,
    "resolved_address": resolved_address,
    "resolution_kind": resolution_meta.get("kind"),
    "target_resolution_failure": resolution_meta.get("target_resolution_failure"),
    "candidate_targets": resolution_meta.get("candidate_targets"),
    "reasoning": reasoning,
    "description": act_desp,
    "duration": int(act_dura) if act_dura is not None else None,
    "source": "decision_translation",
    "created_step": getattr(persona.scratch, "curr_step", None),
    "updated_step": getattr(persona.scratch, "curr_step", None),
    "failure": None,
    "creator_instruction": str(creator_instruction or "").strip() or None,
  }


def _has_inventory_item(persona, target):
  normalized_target = normalize_food_source_target(target)
  item_key = str(normalized_target or "").strip().lower()
  if not item_key:
    return False
  for item_name, count in (getattr(persona.scratch, "inventory", {}) or {}).items():
    try:
      if float(count or 0) <= 0:
        continue
    except Exception:
      continue
    if str(item_name or "").strip().lower() == item_key:
      return True
  return False


def _current_tile_wait_address(persona):
  curr_tile = getattr(persona.scratch, "curr_tile", None)
  if curr_tile and len(curr_tile) >= 2:
    return f"<waiting> {curr_tile[0]} {curr_tile[1]}"
  return getattr(persona.scratch, "living_area", None) or ""


def _build_translation_convergence_hint(persona, intent_memory_summary):
  hint = (
    "Preserve the immediate intent from the natural language thought. "
    "Do not expand into a broader alternative plan. "
  )
  moving_check = getattr(persona.scratch, "is_moving_to_action", None)
  is_in_transit = moving_check() if callable(moving_check) else bool(getattr(persona.scratch, "planned_path", None))
  if is_in_transit:
    hint += (
      "The agent is still in transit from the previous decision, so prefer a translation "
      "that continues the current route unless the thought clearly names a new urgent target. "
    )
  if intent_memory_summary and "No especially relevant prior experience was retrieved." not in str(intent_memory_summary):
    hint += (
      "Relevant experience already helped narrow the choice, so translate to the most direct schema action "
      "instead of exploring many equivalent targets. "
    )
  pending_interrupt = getattr(persona.scratch, "pending_interrupt", None) or {}
  if pending_interrupt:
    hint += (
      f"Reflect the newest change only if it is explicit in the thought. Latest interrupt reason: {pending_interrupt.get('reason')}. "
    )
  return hint


def _get_admin_override_instruction(persona):
  getter = getattr(persona.scratch, "get_admin_override_intent", None)
  if callable(getter):
    return getter()
  intent = str(getattr(persona.scratch, "admin_override_intent", "") or "").strip()
  return intent or None


def _autofill_rest_target(persona, action, target, act_desp, reasoning):
  """When the model wants rest but omits a target, pick a nearby restable object."""
  normalized_skill_id = normalize_skill_id(action, target=target, detail=act_desp)
  if normalized_skill_id != "rest":
    return action, target, act_desp, reasoning
  if str(target or "").strip().lower() not in {"", "none"}:
    return action, target, act_desp, reasoning

  _, matched_target, _ = resolve_candidate_object_address(persona, RESTABLE_OBJECT_TARGETS)
  if matched_target:
    next_detail = act_desp
    if not str(next_detail or "").strip() or str(next_detail).strip().lower() in {
      "idling",
      "idle",
      "resting",
      "idling to conserve energy",
    }:
      next_detail = f"resting at the {matched_target}"
    next_reasoning = f"{reasoning} [rest target auto-filled: {matched_target}]"
    return "Rest", matched_target, next_detail, next_reasoning

  return action, target, act_desp, reasoning


def _autofill_consume_target(persona, action, target, act_desp, reasoning):
  """When the model wants consume but omits a target, prefer food already in inventory."""
  normalized_skill_id = normalize_skill_id(action, target=target, detail=act_desp)
  if normalized_skill_id != "consume":
    return action, target, act_desp, reasoning
  if str(target or "").strip().lower() not in {"", "none"}:
    return action, target, act_desp, reasoning

  inventory = getattr(persona.scratch, "inventory", {}) or {}
  for item_name, count in inventory.items():
    if float(count or 0) <= 0:
      continue
    next_detail = act_desp
    if not str(next_detail or "").strip() or str(next_detail).strip().lower() in {
      "idling",
      "idle",
      "consume",
      "consuming",
    }:
      next_detail = f"eating {item_name} from inventory"
    next_reasoning = f"{reasoning} [consume target auto-filled: {item_name}]"
    return "Consume", str(item_name), next_detail, next_reasoning

  return action, target, act_desp, reasoning


def _autofill_place_target(persona, maze, action, target, act_desp, reasoning):
  """When a place-oriented activity omits a target, choose a reachable place candidate."""
  normalized_skill_id = normalize_skill_id(action, target=target, detail=act_desp)
  candidate_names = PLACE_TARGET_CANDIDATES.get(str(normalized_skill_id or "").strip().lower())
  if not candidate_names:
    return action, target, act_desp, reasoning
  if str(target or "").strip().lower() not in {"", "none"}:
    return action, target, act_desp, reasoning

  _address, matched_target, _kind = resolve_candidate_place_address(persona, maze, normalized_skill_id, candidate_names)
  if not matched_target:
    return action, target, act_desp, reasoning

  next_detail = act_desp
  if not str(next_detail or "").strip() or str(next_detail).strip().lower() in {
    "idling",
    "idle",
    "using",
    "use",
    "working",
    "work",
    "studying",
    "study",
    "wandering",
    "wander",
    "recreate",
  }:
    verb_map = {
      "study": "studying at",
      "work": "working at",
      "use": "using",
      "leisure_use": "spending leisure time at",
      "wander": "wandering through",
    }
    prefix = verb_map.get(normalized_skill_id, "going to")
    next_detail = f"{prefix} the {matched_target}"
  next_reasoning = f"{reasoning} [place target auto-filled: {matched_target}]"
  return action, matched_target, next_detail, next_reasoning


def _normalize_reachable_targets(resources):
  targets = []
  seen = set()
  for resource in resources or []:
    text = str(resource or "").strip()
    if not text:
      continue
    if "(" in text:
      text = text.split("(", 1)[0].strip()
    lowered = text.lower()
    if lowered in seen:
      continue
    seen.add(lowered)
    targets.append(text)
  return sorted(targets, key=lambda item: item.lower())


def _resolve_food_source_address(persona, target):
  if not target:
    return None
  s_mem = getattr(persona, "s_mem", None)
  if not s_mem:
    return None
  addresses = s_mem.find_all_objects(target) if hasattr(s_mem, "find_all_objects") else []
  if not addresses:
    single = s_mem.find_nearest_object(target)
    addresses = [single] if single else []
  world_state = getattr(persona, "world_resource_state", None)
  for address in addresses:
    if not world_state or world_state.is_available(address):
      return address
  return addresses[0] if addresses else None


def _describe_resource_state(persona, obj, address=None):
  world_state = getattr(persona, "world_resource_state", None)
  canonical_target = normalize_food_source_target(obj)
  if not world_state or canonical_target not in VALID_GATHER_FOOD_SOURCES:
    return "normal"
  source_address = address or _resolve_food_source_address(persona, canonical_target)
  if source_address:
    return f"stock: {world_state.describe_address(source_address)}"
  return "stock: unknown"


def _inventory_state_label(inventory):
  has_items = False
  for value in (inventory or {}).values():
    try:
      if int(value) > 0:
        has_items = True
        break
    except Exception:
      continue
  return "has_food" if has_items else "empty"


def _cooperative_state_label(cooperative_context):
  return "none" if "No special cooperative tasks or wait states are active nearby." in str(cooperative_context or "") else "active"


def _build_decision_state_signature(persona, intent_family, object_states, cooperative_context):
  failure_getter = getattr(persona.scratch, "get_recent_navigation_failure", None)
  if callable(failure_getter) and failure_getter():
    return None
  if intent_family not in {"restore_satiety", "restore_stamina", "restore_health"}:
    return None
  return build_state_signature(
    persona_name=persona.name,
    intent_family=intent_family,
    satiety=persona.scratch.satiety,
    stamina=persona.scratch.stamina,
    health=persona.scratch.health,
    mood=persona.scratch.mood,
    inventory_state=_inventory_state_label(getattr(persona.scratch, "inventory", {}) or {}),
    reachable_targets=_normalize_reachable_targets(object_states),
    cooperative_state=_cooperative_state_label(cooperative_context),
  )


def _merge_timing_meta(base_meta, extra_meta):
  merged = dict(base_meta or {})
  for key, value in (extra_meta or {}).items():
    try:
      merged[key] = float(merged.get(key, 0.0) or 0.0) + float(value or 0.0)
    except Exception:
      merged[key] = value
  return merged


def _build_decision_id(persona):
  persona_label = str(getattr(persona, "name", "persona")).strip().replace(" ", "_")
  curr_step = getattr(getattr(persona, "scratch", None), "curr_step", None)
  return f"{persona_label}-{curr_step}-{uuid.uuid4().hex[:8]}"


def _build_minimal_filter_summary(persona, object_states, decision_timing_meta=None):
  invalid_targets = build_invalid_targets(getattr(persona, "scratch", None))
  filtered_resources = filter_invalid_resources(object_states, invalid_targets)
  original_count = len(list(object_states or []))
  filtered_count = len(list(filtered_resources or []))
  removed_count = max(0, original_count - filtered_count)
  retry_triggered = bool((decision_timing_meta or {}).get("constraint_hits", 0))
  return {
    "enabled": True,
    "applied": bool(invalid_targets or removed_count or retry_triggered),
    "invalid_targets": invalid_targets,
    "invalid_target_count": len(invalid_targets),
    "resource_filter_applied": removed_count > 0,
    "removed_resource_count": removed_count,
    "output_validation_enabled": True,
    "retry_triggered": retry_triggered,
  }


def _run_decision_pipeline(persona,
                           object_states,
                           temporal_context,
                           status_summary,
                           physiological_rules,
                           cooperative_context,
                           last_action_desc,
                           intent_memory_summary,
                           admin_override_instruction=None,
                           intent_family=None,
                           decision_id=None,
                           decision_convergence_hint=None,
                           allow_retry=True,
                           static_resource_context_text=None):
  base_translation_hint = _build_translation_convergence_hint(persona, intent_memory_summary)
  translation_convergence_hint = base_translation_hint
  if decision_convergence_hint:
    translation_convergence_hint = f"{base_translation_hint} {decision_convergence_hint}".strip()
  invalid_targets = build_invalid_targets(persona.scratch)
  use_joint_decision = os.getenv("ENABLE_JOINT_DECISION_PIPELINE", "0") == "1"
  use_semantic_cache = (
    os.getenv("ENABLE_SEMANTIC_DECISION_CACHE", "0") == "1"
    and not admin_override_instruction
  )
  timing_meta = {
    "decision_cache_lookup": 0.0,
    "decision_cache_hit": 0.0,
    "joint_decision": 0.0,
    "demand_thinking": 0.0,
    "action_translation": 0.0,
    "constraint_hits": 0.0,
    "last_retry_reason": "",
  }
  cache_signature = None
  decision_request_config = get_default_decision_request_config()

  if use_semantic_cache:
    stage_started_at = time.perf_counter()
    cache_signature = _build_decision_state_signature(
      persona,
      intent_family,
      object_states,
      cooperative_context,
    )
    cached_decision = get_cached_decision(cache_signature) if cache_signature else None
    timing_meta["decision_cache_lookup"] = _elapsed_ms(stage_started_at)
    if cached_decision:
      timing_meta["decision_cache_hit"] = 1.0
      thinking_text = str(cached_decision.get("thought") or cached_decision.get("detail") or "I should pause briefly.").strip()
      return thinking_text, cached_decision, translation_convergence_hint, False, timing_meta, cache_signature

  if use_joint_decision:
    stage_started_at = time.perf_counter()
    joint_result = run_gpt_prompt_joint_decision(
      persona,
      object_states,
      temporal_context=temporal_context,
      status_summary=status_summary,
      rules=physiological_rules,
      cooperative_context=cooperative_context,
      last_action_desc=last_action_desc,
      intent_memory_summary=intent_memory_summary,
      admin_override_instruction=admin_override_instruction,
      decision_convergence_hint=translation_convergence_hint,
      decision_id=decision_id,
      static_resource_context_text=static_resource_context_text,
      request_config=decision_request_config,
    )
    timing_meta["joint_decision"] = _elapsed_ms(stage_started_at)
    if isinstance(joint_result, dict) and joint_result.get("action"):
      should_retry, retry_reason = validate_decision_target(joint_result, invalid_targets)
      if should_retry and allow_retry:
        retry_hint = build_retry_feedback(retry_reason)
        timing_meta["constraint_hits"] = 1.0
        timing_meta["last_retry_reason"] = retry_reason
        minimal_filter_summary = _build_minimal_filter_summary(persona, object_states, decision_timing_meta=timing_meta)
        append_debug_log(
          "decision_constraint_hits.jsonl",
          {
            "persona": persona.name,
            "step": getattr(persona.scratch, "curr_step", None),
            "invalid_targets": invalid_targets,
            "original_decision": joint_result,
            "retry_reason": retry_reason,
            "pipeline": "joint_decision",
            "minimal_filter_enabled": bool(minimal_filter_summary.get("enabled")),
            "minimal_filter_applied": bool(minimal_filter_summary.get("applied")),
            "minimal_filter_summary": minimal_filter_summary,
          },
        )
        retry_thinking_text, retry_decision, retry_hint_text, retry_used_joint, retry_timing_meta, retry_cache_signature = _run_decision_pipeline(
          persona,
          object_states,
          temporal_context,
          status_summary,
          physiological_rules,
          cooperative_context,
          last_action_desc,
          intent_memory_summary,
          admin_override_instruction=admin_override_instruction,
          intent_family=intent_family,
          decision_id=decision_id,
          decision_convergence_hint=retry_hint,
          allow_retry=False,
          static_resource_context_text=static_resource_context_text,
        )
        return retry_thinking_text, retry_decision, retry_hint_text, retry_used_joint, _merge_timing_meta(timing_meta, retry_timing_meta), retry_cache_signature
      thinking_text = str(joint_result.get("thought") or "").strip()
      if not thinking_text:
        thinking_text = str(joint_result.get("detail") or "I should pause briefly.").strip()
      return thinking_text, joint_result, translation_convergence_hint, True, timing_meta, cache_signature

  stage_started_at = time.perf_counter()
  thinking_text = run_gpt_prompt_demand_thinking(
      persona,
      object_states,
      temporal_context=temporal_context,
      status_summary=status_summary,
      rules=physiological_rules,
      cooperative_context=cooperative_context,
      last_action_desc=last_action_desc,
      intent_memory_summary=intent_memory_summary,
      admin_override_instruction=admin_override_instruction,
      decision_id=decision_id,
      static_resource_context_text=static_resource_context_text,
      request_config=decision_request_config,
  )
  timing_meta["demand_thinking"] = _elapsed_ms(stage_started_at)
  stage_started_at = time.perf_counter()
  decision = run_gpt_prompt_action_translation(
      thinking_text,
      object_states,
      persona.scratch.get_str_firstname(),
      admin_override_instruction=admin_override_instruction,
      decision_convergence_hint=translation_convergence_hint,
      retry_count=1,
      decision_id=decision_id,
      persona=persona,
      request_config=decision_request_config,
  )
  timing_meta["action_translation"] = _elapsed_ms(stage_started_at)
  should_retry, retry_reason = validate_decision_target(decision, invalid_targets)
  if should_retry and allow_retry:
    retry_hint = build_retry_feedback(retry_reason)
    timing_meta["constraint_hits"] = 1.0
    timing_meta["last_retry_reason"] = retry_reason
    minimal_filter_summary = _build_minimal_filter_summary(persona, object_states, decision_timing_meta=timing_meta)
    append_debug_log(
      "decision_constraint_hits.jsonl",
      {
        "persona": persona.name,
        "step": getattr(persona.scratch, "curr_step", None),
        "invalid_targets": invalid_targets,
        "original_decision": decision,
        "retry_reason": retry_reason,
        "pipeline": "thinking_translation",
        "minimal_filter_enabled": bool(minimal_filter_summary.get("enabled")),
        "minimal_filter_applied": bool(minimal_filter_summary.get("applied")),
        "minimal_filter_summary": minimal_filter_summary,
      },
    )
    retry_thinking_text, retry_decision, retry_hint_text, retry_used_joint, retry_timing_meta, retry_cache_signature = _run_decision_pipeline(
      persona,
      object_states,
      temporal_context,
      status_summary,
      physiological_rules,
      cooperative_context,
      last_action_desc,
      intent_memory_summary,
      admin_override_instruction=admin_override_instruction,
      intent_family=intent_family,
      decision_id=decision_id,
      decision_convergence_hint=retry_hint,
      allow_retry=False,
      static_resource_context_text=static_resource_context_text,
    )
    return retry_thinking_text, retry_decision, retry_hint_text, retry_used_joint, _merge_timing_meta(timing_meta, retry_timing_meta), retry_cache_signature
  return thinking_text, decision, translation_convergence_hint, False, timing_meta, cache_signature


def _infer_object_state_phrase(act_game_object, act_desp):
  obj = str(act_game_object or "object").strip() or "object"
  desc = str(act_desp or "").lower()
  if "being opened" in desc or "is opened" in desc:
    return "being opened"
  if "being used for eating" in desc:
    return "being used for eating"
  if "being used for recovery" in desc:
    return "being used for recovery"
  if "being used for work" in desc:
    return "being used for work"
  if "being used" in desc:
    return "being used"
  if any(keyword in desc for keyword in ["gather", "opening", "open", "retrieve", "fetch"]):
    return "being opened"
  if any(keyword in desc for keyword in ["consume", "eating", "eat", "drink", "meal", "snack"]):
    return "being used for eating"
  if any(keyword in desc for keyword in ["rest", "sleep", "lying", "nap", "wash", "cleaning hands"]):
    return "being used for recovery"
  if any(keyword in desc for keyword in ["study", "write", "work", "research"]):
    return "being used for work"
  if any(keyword in desc for keyword in ["sing", "music", "piano", "tv", "game", "exercise", "fitness", "use"]):
    return "being used"
  return "being used"


def build_act_obj_state(act_game_object, act_desp, persona):
  cache_key = (
    str(act_game_object or "").strip().lower(),
    str(act_desp or "").strip().lower(),
  )
  cached = _ACT_OBJ_STATE_CACHE.get(cache_key)
  if cached:
    return cached

  phrase = _infer_object_state_phrase(act_game_object, act_desp)
  obj = str(act_game_object or "object").strip() or "object"
  desc = f"{obj} is {phrase}"
  event = (obj, "is", phrase)
  _ACT_OBJ_STATE_CACHE[cache_key] = (desc, event)
  return desc, event

def generate_wake_up_hour(persona):
  """
  Generates the time when the persona wakes up. This becomes an integral part
  of our process for generating the persona's daily plan.
  
  Persona state: identity stable set, lifestyle, first_name

  INPUT: 
    persona: The Persona class instance 
  OUTPUT: 
    an integer signifying the persona's wake up hour
  EXAMPLE OUTPUT: 
    8
  """
  if debug: print ("GNS FUNCTION: <generate_wake_up_hour>")
  return int(run_gpt_prompt_wake_up_hour(persona)[0])


def generate_first_daily_plan(persona, wake_up_hour): 
  """
  Generates the daily plan for the persona. 
  Basically the long term planning that spans a day. Returns a list of actions
  that the persona will take today. Usually comes in the following form: 
  'wake up and complete the morning routine at 6:00 am', 
  'eat breakfast at 7:00 am',.. 
  Note that the actions come without a period. 

  Persona state: identity stable set, lifestyle, cur_data_str, first_name

  INPUT: 
    persona: The Persona class instance 
    wake_up_hour: an integer that indicates when the hour the persona wakes up 
                  (e.g., 8)
  OUTPUT: 
    a list of daily actions in broad strokes.
  EXAMPLE OUTPUT: 
    ['wake up and complete the morning routine at 6:00 am', 
     'have breakfast and brush teeth at 6:30 am',
     'work on painting project from 8:00 am to 12:00 pm', 
     'have lunch at 12:00 pm', 
     'take a break and watch TV from 2:00 pm to 4:00 pm', 
     'work on painting project from 4:00 pm to 6:00 pm', 
     'have dinner at 6:00 pm', 'watch TV from 7:00 pm to 8:00 pm']
  """
  if debug: print ("GNS FUNCTION: <generate_first_daily_plan>")
  return run_gpt_prompt_daily_plan(persona, wake_up_hour)[0]


def generate_hourly_schedule(persona, wake_up_hour): 
  """
  Based on the daily req, creates an hourly schedule -- one hour at a time. 
  The form of the action for each of the hour is something like below: 
  "sleeping in her bed"
  
  The output is basically meant to finish the phrase, "x is..."

  Persona state: identity stable set, daily_plan

  INPUT: 
    persona: The Persona class instance 
    persona: Integer form of the wake up hour for the persona.  
  OUTPUT: 
    a list of activities and their duration in minutes: 
  EXAMPLE OUTPUT: 
    [['sleeping', 360], ['waking up and starting her morning routine', 60], 
     ['eating breakfast', 60],..
  """
  if debug: print ("GNS FUNCTION: <generate_hourly_schedule>")

  hour_str = ["00:00 AM", "01:00 AM", "02:00 AM", "03:00 AM", "04:00 AM", 
              "05:00 AM", "06:00 AM", "07:00 AM", "08:00 AM", "09:00 AM", 
              "10:00 AM", "11:00 AM", "12:00 PM", "01:00 PM", "02:00 PM", 
              "03:00 PM", "04:00 PM", "05:00 PM", "06:00 PM", "07:00 PM",
              "08:00 PM", "09:00 PM", "10:00 PM", "11:00 PM"]
  n_m1_activity = []
  diversity_repeat_count = 3
  for i in range(diversity_repeat_count): 
    n_m1_activity_set = set(n_m1_activity)
    if len(n_m1_activity_set) < 5: 
      n_m1_activity = []
      for count, curr_hour_str in enumerate(hour_str): 
        if wake_up_hour > 0: 
          n_m1_activity += ["sleeping"]
          wake_up_hour -= 1
        else: 
          n_m1_activity += [run_gpt_prompt_generate_hourly_schedule(
                          persona, curr_hour_str, n_m1_activity, hour_str)[0]]
  
  # Step 1. Compressing the hourly schedule to the following format: 
  # The integer indicates the number of hours. They should add up to 24. 
  # [['sleeping', 6], ['waking up and starting her morning routine', 1], 
  # ['eating breakfast', 1], ['getting ready for the day', 1], 
  # ['working on her painting', 2], ['taking a break', 1], 
  # ['having lunch', 1], ['working on her painting', 3], 
  # ['taking a break', 2], ['working on her painting', 2], 
  # ['relaxing and watching TV', 1], ['going to bed', 1], ['sleeping', 2]]
  _n_m1_hourly_compressed = []
  prev = None 
  prev_count = 0
  for i in n_m1_activity: 
    if i != prev:
      prev_count = 1 
      _n_m1_hourly_compressed += [[i, prev_count]]
      prev = i
    else: 
      if _n_m1_hourly_compressed: 
        _n_m1_hourly_compressed[-1][1] += 1

  # Step 2. Expand to min scale (from hour scale)
  # [['sleeping', 360], ['waking up and starting her morning routine', 60], 
  # ['eating breakfast', 60],..
  n_m1_hourly_compressed = []
  for task, duration in _n_m1_hourly_compressed: 
    n_m1_hourly_compressed += [[task, duration*60]]

  return n_m1_hourly_compressed


def generate_task_decomp(persona, task, duration): 
  """
  A few shot decomposition of a task given the task description 

  Persona state: identity stable set, curr_date_str, first_name

  INPUT: 
    persona: The Persona class instance 
    task: the description of the task at hand in str form
          (e.g., "waking up and starting her morning routine")
    duration: an integer that indicates the number of minutes this task is 
              meant to last (e.g., 60)
  OUTPUT: 
    a list of list where the inner list contains the decomposed task 
    description and the number of minutes the task is supposed to last. 
  EXAMPLE OUTPUT: 
    [['going to the bathroom', 5], ['getting dressed', 5], 
     ['eating breakfast', 15], ['checking her email', 5], 
     ['getting her supplies ready for the day', 15], 
     ['starting to work on her painting', 15]] 

  """
  if debug: print ("GNS FUNCTION: <generate_task_decomp>")
  return run_gpt_prompt_task_decomp(persona, task, duration)[0]


def generate_action_sector(act_desp, persona, maze): 
  """TODO 
  Given the persona and the task description, choose the action_sector. 

  Persona state: identity stable set, n-1 day schedule, daily plan

  INPUT: 
    act_desp: description of the new action (e.g., "sleeping")
    persona: The Persona class instance 
  OUTPUT: 
    action_arena (e.g., "bedroom 2")
  EXAMPLE OUTPUT: 
    "bedroom 2"
  """
  if debug: print ("GNS FUNCTION: <generate_action_sector>")
  return run_gpt_prompt_action_sector(act_desp, persona, maze)[0]


def generate_action_arena(act_desp, persona, maze, act_world, act_sector): 
  """TODO 
  Given the persona and the task description, choose the action_arena. 

  Persona state: identity stable set, n-1 day schedule, daily plan

  INPUT: 
    act_desp: description of the new action (e.g., "sleeping")
    persona: The Persona class instance 
  OUTPUT: 
    action_arena (e.g., "bedroom 2")
  EXAMPLE OUTPUT: 
    "bedroom 2"
  """
  if debug: print ("GNS FUNCTION: <generate_action_arena>")
  return run_gpt_prompt_action_arena(act_desp, persona, maze, act_world, act_sector)[0]


def generate_action_game_object(act_desp, act_address, persona, maze):
  """TODO
  Given the action description and the act address (the address where
  we expect the action to task place), choose one of the game objects. 

  Persona state: identity stable set, n-1 day schedule, daily plan

  INPUT: 
    act_desp: the description of the action (e.g., "sleeping")
    act_address: the arena where the action will take place: 
               (e.g., "dolores double studio:double studio:bedroom 2")
    persona: The Persona class instance 
  OUTPUT: 
    act_game_object: 
  EXAMPLE OUTPUT: 
    "bed"
  """
  if debug: print ("GNS FUNCTION: <generate_action_game_object>")
  if not persona.s_mem.get_str_accessible_arena_game_objects(act_address): 
    return "<random>"
  return run_gpt_prompt_action_game_object(act_desp, persona, maze, act_address)[0]


def generate_action_pronunciatio(act_desp, persona): 
  """TODO 
  Given an action description, creates an emoji string description via a few
  shot prompt. 

  Does not really need any information from persona. 

  INPUT: 
    act_desp: the description of the action (e.g., "sleeping")
    persona: The Persona class instance
  OUTPUT: 
    a string of emoji that translates action description.
  EXAMPLE OUTPUT: 
    "🧈🍞"
  """
  if debug: print ("GNS FUNCTION: <generate_action_pronunciatio>")
  desc = str(act_desp or "").lower()

  emoji_rules = [
    (["chat", "talk", "conversation"], "💬"),
    (["sleep", "bed", "rest", "nap"], "🛌"),
    (["refrigerator", "fridge", "gather food", "food items"], "🍎"),
    (["eat", "consume", "meal", "snack", "drink"], "🍴"),
    (["stove", "cook", "cooking", "prepare food"], "🍳"),
    (["apple tree", "apples", "harvest"], "🍎"),
    (["cafe counter", "coffee", "brew"], "☕"),
    (["library", "study", "research", "write", "computer", "desk"], "📚"),
    (["work", "office", "classroom"], "💼"),
    (["piano", "sing", "music", "guitar", "harp"], "🎵"),
    (["game console", "tv", "television", "pool table"], "🎮"),
    (["lifting weight", "exercise", "fitness", "workout"], "🏋️"),
    (["walk", "go to", "moving"], "🚶"),
  ]

  for keywords, emoji in emoji_rules:
    if any(keyword in desc for keyword in keywords):
      return emoji
  return "🙂"


def _describe_satiety(satiety):
  if satiety >= 90:
    return ("well fed", "Your stomach feels full and stable.", "Food does not need your attention right now.", "Hunger is not a meaningful concern at the moment.")
  if satiety >= 70:
    return ("slightly hungry", "You notice a mild appetite, but it is easy to ignore.", "You can continue normal activity while casually keeping food in mind.", "If this keeps dropping, food will start competing with other goals.")
  if satiety >= 50:
    return ("hungry", "You feel noticeably hungry and food is starting to sound appealing.", "Eating should enter your near-term plan.", "If ignored, hunger may begin to distort priorities.")
  if satiety >= 30:
    return ("clearly hungry", "You feel clearly hungry and food is becoming harder to ignore.", "Finding food should become your main near-term priority. Leisure, exercise, or emotional unwinding should usually wait until you have secured food.", "If this continues to drop, the body will become weak and health may eventually suffer.")
  if satiety >= 15:
    return ("severely hungry", "Your hunger is intense and physically distracting.", "Getting food should outweigh leisure, exploration, or exercise.", "Continuing to ignore food now risks a rapid slide toward physical danger.")
  return ("starving", "Your body feels close to starvation and survival is in danger.", "You should treat obtaining food as the immediate priority.", "If this keeps falling, health damage and death become imminent.")


def _describe_stamina(stamina):
  if stamina >= 90:
    return ("energetic", "You feel physically fresh and capable.", "High-effort activity is fully manageable.", "Fatigue is not currently limiting your choices.")
  if stamina >= 70:
    return ("steady", "Your body still feels capable and responsive.", "Work, travel, and active tasks remain reasonable.", "Rest is not urgent yet.")
  if stamina >= 50:
    return ("somewhat tired", "You can feel fatigue building in the background.", "You can continue acting, but rest should begin entering your planning horizon.", "If you keep spending energy, your next choices may narrow.")
  if stamina >= 30:
    return ("tired", "You feel distinctly tired and less resilient.", "High-effort activity is becoming a worse tradeoff than rest.", "If stamina keeps dropping, recovery will soon need priority.")
  if stamina >= 15:
    return ("very exhausted", "Your body feels heavily drained.", "Rest should outweigh optional activity.", "Ignoring fatigue now risks poor choices and escalating physical strain.")
  return ("exhausted", "You feel close to collapse from fatigue.", "Rest should be treated as an immediate need.", "Continuing activity now is physically unsafe.")


def _describe_health(health):
  if health >= 90:
    return ("feeling healthy", "Your body feels normal and uninjured.", "You do not need to prioritize treatment.", "Health is stable right now.")
  if health >= 70:
    return ("lightly injured", "You feel some discomfort or minor injury.", "You can still act, but recovery should stay on your radar.", "Further strain may worsen your condition.")
  if health >= 50:
    return ("injured", "Your body feels hurt enough to affect judgment and comfort.", "Recovery and safer choices should become more important.", "Pushing too hard may deepen the injury.")
  if health >= 30:
    return ("badly injured", "Your body feels seriously hurt and vulnerable.", "Treatment and safety should become a high-priority concern.", "Risky activity may sharply worsen your condition.")
  if health >= 15:
    return ("dangerously injured", "Your physical condition feels dangerous.", "Survival-oriented recovery should outweigh ordinary goals.", "Ignoring treatment could push you toward collapse.")
  return ("near collapse", "Your body feels close to breaking down.", "Preserving life and seeking recovery should override almost everything else.", "Further harm could be fatal.")


def _describe_mood(mood):
  if mood >= 90:
    return ("very positive", "You feel upbeat, receptive, and open to enjoyable activity.", "Leisure, curiosity, and social behavior feel naturally appealing.", "Mood is not a limiting factor.")
  if mood >= 60:
    return ("stable", "Your mood feels steady and workable.", "You can engage normally with work, people, or leisure.", "Mood does not currently demand attention.")
  if mood >= 40:
    return ("slightly low", "You feel a little emotionally flat.", "Pleasant activity or social contact may become more attractive.", "If this declines further, motivation may weaken.")
  if mood >= 30:
    return ("low", "You feel noticeably low and less motivated.", "Mood-repairing activity should start to compete with neutral tasks.", "If ignored, you may become more avoidant or passive.")
  if mood >= 15:
    return ("very low", "You feel emotionally strained and unhappy.", "Comfort, support, or restorative activity should rise in priority.", "Low mood may start to distort decision quality.")
  return ("near breakdown", "You feel emotionally overwhelmed.", "Immediate relief, support, or emotional recovery should matter greatly.", "If this worsens, normal decision-making may become unstable.")


def _build_homeostasis_status_summary(persona):
  """Builds descriptive homeostasis text so the LLM sees feelings and urgency, not just raw numbers."""
  motive_result = select_motives(persona.scratch.get_motive_attributes_snapshot())
  satiety = float(persona.scratch.satiety)
  stamina = float(persona.scratch.stamina)
  health = float(persona.scratch.health)
  mood = float(persona.scratch.mood)

  satiety_label, satiety_feel, satiety_hint, satiety_risk = _describe_satiety(satiety)
  stamina_label, stamina_feel, stamina_hint, stamina_risk = _describe_stamina(stamina)
  health_label, health_feel, health_hint, health_risk = _describe_health(health)
  mood_label, mood_feel, mood_hint, mood_risk = _describe_mood(mood)

  priorities = [
    ("satiety", satiety, 100.0 - satiety, satiety_label),
    ("stamina", stamina, 100.0 - stamina, stamina_label),
    ("health", health, 100.0 - health, health_label),
    ("mood", mood, 100.0 - mood, mood_label),
  ]
  priorities.sort(key=lambda item: item[2], reverse=True)
  top_need, top_value, _, top_label = priorities[0]

  if top_need == "satiety" and satiety < 50:
    overall_summary = (
      f"Overall Summary: You are still functional overall, but hunger is currently the most pressing need. "
      f"With Satiety at {satiety:.1f}, getting food should usually be your next action and should outweigh leisure, exercise, or emotional comfort unless another need is in immediate crisis."
    )
  elif top_need == "stamina" and stamina < 50:
    overall_summary = (
      f"Overall Summary: Fatigue is the most pressing internal pressure right now. "
      f"With Stamina at {stamina:.1f}, rest should compete strongly against optional activity."
    )
  elif top_need == "health" and health < 70:
    overall_summary = (
      f"Overall Summary: Physical recovery and safety should weigh heavily in your choices. "
      f"With Health at {health:.1f}, risky or strenuous activity deserves caution."
    )
  elif top_need == "mood" and mood < 60 and satiety >= 70 and stamina >= 50 and health >= 70:
    overall_summary = (
      f"Overall Summary: Your body is safe and well supplied, but your mood is lagging behind. "
      f"With Mood at {mood:.1f} and Satiety at {satiety:.1f}, enjoyable leisure or social contact should usually beat neutral work or more food gathering."
    )
  elif top_need == "mood":
    overall_summary = (
      f"Overall Summary: Emotional recovery is becoming a meaningful need. "
      f"With Mood at {mood:.1f}, comforting or restorative activity should become more attractive."
    )
  else:
    overall_summary = (
      f"Overall Summary: Your most noticeable internal signal right now is {top_need} ({top_label}) at {top_value:.1f}. "
      f"Keep that pressure in mind when choosing your next action."
    )

  return "\n".join([
    f"- Dominant Motive: {motive_result.get('motive_sentence') or '暂无明显主动机。'}",
    f"- Satiety Interpretation: {satiety_label}. Feeling: {satiety_feel} Behavioral Hint: {satiety_hint} Risk: {satiety_risk}",
    f"- Stamina Interpretation: {stamina_label}. Feeling: {stamina_feel} Behavioral Hint: {stamina_hint} Risk: {stamina_risk}",
    f"- Health Interpretation: {health_label}. Feeling: {health_feel} Behavioral Hint: {health_hint} Risk: {health_risk}",
    f"- Mood Interpretation: {mood_label}. Feeling: {mood_feel} Behavioral Hint: {mood_hint} Risk: {mood_risk}",
    overall_summary,
  ])


def generate_action_event_triple(act_desp, persona): 
  """TODO 

  INPUT: 
    act_desp: the description of the action (e.g., "sleeping")
    persona: The Persona class instance
  OUTPUT: 
    a string of emoji that translates action description.
  EXAMPLE OUTPUT: 
    "🧈🍞"
  """
  if debug: print ("GNS FUNCTION: <generate_action_event_triple>")
  return run_gpt_prompt_event_triple(act_desp, persona)[0]


def generate_act_obj_desc(act_game_object, act_desp, persona): 
  if debug: print ("GNS FUNCTION: <generate_act_obj_desc>")
  return build_act_obj_state(act_game_object, act_desp, persona)[0]


def generate_act_obj_event_triple(act_game_object, act_obj_desc, persona): 
  if debug: print ("GNS FUNCTION: <generate_act_obj_event_triple>")
  return build_act_obj_state(act_game_object, act_obj_desc, persona)[1]




def generate_convo_summary(persona, convo): 
  convo_summary = run_gpt_prompt_summarize_conversation(persona, convo)[0]
  return convo_summary


def generate_decide_to_talk(init_persona, target_persona, retrieved): 
  x =run_gpt_prompt_decide_to_talk(init_persona, target_persona, retrieved)[0]
  if debug: print ("GNS FUNCTION: <generate_decide_to_talk>")

  if x == "yes": 
    return True
  else: 
    return False


def generate_decide_to_react(init_persona, target_persona, retrieved): 
  if debug: print ("GNS FUNCTION: <generate_decide_to_react>")
  return run_gpt_prompt_decide_to_react(init_persona, target_persona, retrieved)[0]


def generate_new_decomp_schedule(persona, inserted_act, inserted_act_dur,  start_hour, end_hour): 
  # Step 1: Setting up the core variables for the function. 
  # <p> is the persona whose schedule we are editing right now. 
  p = persona
  # <today_min_pass> indicates the number of minutes that have passed today. 
  today_min_pass = (int(p.scratch.curr_time.hour) * 60 
                    + int(p.scratch.curr_time.minute) + 1)
  
  # Step 2: We need to create <main_act_dur> and <truncated_act_dur>. 
  # These are basically a sub-component of <f_daily_schedule> of the persona,
  # but focusing on the current decomposition. 
  # Here is an example for <main_act_dur>: 
  # ['wakes up and completes her morning routine (wakes up at 6am)', 5]
  # ['wakes up and completes her morning routine (wakes up at 6am)', 5]
  # ['wakes up and completes her morning routine (uses the restroom)', 5]
  # ['wakes up and completes her morning routine (washes her ...)', 10]
  # ['wakes up and completes her morning routine (makes her bed)', 5]
  # ['wakes up and completes her morning routine (eats breakfast)', 15]
  # ['wakes up and completes her morning routine (gets dressed)', 10]
  # ['wakes up and completes her morning routine (leaves her ...)', 5]
  # ['wakes up and completes her morning routine (starts her ...)', 5]
  # ['preparing for her day (waking up at 6am)', 5]
  # ['preparing for her day (making her bed)', 5]
  # ['preparing for her day (taking a shower)', 15]
  # ['preparing for her day (getting dressed)', 5]
  # ['preparing for her day (eating breakfast)', 10]
  # ['preparing for her day (brushing her teeth)', 5]
  # ['preparing for her day (making coffee)', 5]
  # ['preparing for her day (checking her email)', 5]
  # ['preparing for her day (starting to work on her painting)', 5]
  # 
  # And <truncated_act_dur> concerns only until where an event happens. 
  # ['wakes up and completes her morning routine (wakes up at 6am)', 5]
  # ['wakes up and completes her morning routine (wakes up at 6am)', 2]
  main_act_dur = []
  truncated_act_dur = []
  dur_sum = 0 # duration sum
  count = 0 # enumerate count
  truncated_fin = False 


  for act, dur in p.scratch.f_daily_schedule: 
    if (dur_sum >= start_hour * 60) and (dur_sum < end_hour * 60): 
      main_act_dur += [[act, dur]]
      if dur_sum <= today_min_pass:
        truncated_act_dur += [[act, dur]]
      elif dur_sum > today_min_pass and not truncated_fin: 
        # We need to insert that last act, duration list like this one: 
        # e.g., ['wakes up and completes her morning routine (wakes up...)', 2]
        truncated_act_dur += [[p.scratch.f_daily_schedule[count][0], 
                               dur_sum - today_min_pass]] 
        truncated_act_dur[-1][-1] -= (dur_sum - today_min_pass) ######## DEC 7 DEBUG;.. is the +1 the right thing to do??? 
        # truncated_act_dur[-1][-1] -= (dur_sum - today_min_pass + 1) ######## DEC 7 DEBUG;.. is the +1 the right thing to do??? 


        # truncated_act_dur[-1][-1] -= (dur_sum - today_min_pass) ######## DEC 7 DEBUG;.. is the +1 the right thing to do??? 
        truncated_fin = True
    dur_sum += dur
    count += 1

  persona_name = persona.name 
  main_act_dur = main_act_dur

  x = truncated_act_dur[-1][0].split("(")[0].strip() + " (on the way to " + truncated_act_dur[-1][0].split("(")[-1][:-1] + ")"
  truncated_act_dur[-1][0] = x 

  if "(" in truncated_act_dur[-1][0]: 
    inserted_act = truncated_act_dur[-1][0].split("(")[0].strip() + " (" + inserted_act + ")"

  # To do inserted_act_dur+1 below is an important decision but I'm not sure
  # if I understand the full extent of its implications. Might want to 
  # revisit. 
  truncated_act_dur += [[inserted_act, inserted_act_dur]]
  start_time_hour = (datetime.datetime(2022, 10, 31, 0, 0) 
                   + datetime.timedelta(hours=start_hour))
  end_time_hour = (datetime.datetime(2022, 10, 31, 0, 0) 
                   + datetime.timedelta(hours=end_hour))

  if debug: print ("GNS FUNCTION: <generate_new_decomp_schedule>")
  return run_gpt_prompt_new_decomp_schedule(persona, 
                                            main_act_dur, 
                                            truncated_act_dur, 
                                            start_time_hour,
                                            end_time_hour,
                                            inserted_act,
                                            inserted_act_dur)[0]


##############################################################################
# CHAPTER 3: Plan
##############################################################################

def revise_identity(persona): 
  p_name = persona.scratch.name

  focal_points = [f"{p_name}'s plan for {persona.scratch.get_str_curr_date_str()}.",
                  f"Important recent events for {p_name}'s life."]
  retrieved = new_retrieve(persona, focal_points)

  statements = "[Statements]\n"
  for key, val in retrieved.items():
    for i in val: 
      statements += f"{i.created.strftime('%A %B %d -- %H:%M %p')}: {i.embedding_key}\n"

  # print (";adjhfno;asdjao;idfjo;af", p_name)
  plan_prompt = statements + "\n"
  plan_prompt += f"Given the statements above, is there anything that {p_name} should remember as they plan for"
  plan_prompt += f" *{persona.scratch.curr_time.strftime('%A %B %d')}*? "
  plan_prompt += f"If there is any scheduling information, be as specific as possible (include date, time, and location if stated in the statement)\n\n"
  plan_prompt += f"Write the response from {p_name}'s perspective."
  plan_note = ChatGPT_single_request(plan_prompt)
  # print (plan_note)

  thought_prompt = statements + "\n"
  thought_prompt += f"Given the statements above, how might we summarize {p_name}'s feelings about their days up to now?\n\n"
  thought_prompt += f"Write the response from {p_name}'s perspective."
  thought_note = ChatGPT_single_request(thought_prompt)
  # print (thought_note)

  currently_prompt = f"{p_name}'s status from {(persona.scratch.curr_time - datetime.timedelta(days=1)).strftime('%A %B %d')}:\n"
  currently_prompt += f"{persona.scratch.currently}\n\n"
  currently_prompt += f"{p_name}'s thoughts at the end of {(persona.scratch.curr_time - datetime.timedelta(days=1)).strftime('%A %B %d')}:\n" 
  currently_prompt += (plan_note + thought_note).replace('\n', '') + "\n\n"
  currently_prompt += f"It is now {persona.scratch.curr_time.strftime('%A %B %d')}. Given the above, write {p_name}'s status for {persona.scratch.curr_time.strftime('%A %B %d')} that reflects {p_name}'s thoughts at the end of {(persona.scratch.curr_time - datetime.timedelta(days=1)).strftime('%A %B %d')}. Write this in third-person talking about {p_name}."
  currently_prompt += f"If there is any scheduling information, be as specific as possible (include date, time, and location if stated in the statement).\n\n"
  currently_prompt += "Follow this format below:\nStatus: <new status>"
  # print ("DEBUG ;adjhfno;asdjao;asdfsidfjo;af", p_name)
  # print (currently_prompt)
  new_currently = ChatGPT_single_request(currently_prompt)
  # print (new_currently)
  # print (new_currently[10:])

  persona.scratch.currently = new_currently

  daily_req_prompt = persona.scratch.get_str_iss() + "\n"
  daily_req_prompt += f"Today is {persona.scratch.curr_time.strftime('%A %B %d')}. Here is {persona.scratch.name}'s plan today in broad-strokes (with the time of the day. e.g., have a lunch at 12:00 pm, watch TV from 7 to 8 pm).\n\n"
  daily_req_prompt += f"Follow this format (the list should have 4~6 items but no more):\n"
  daily_req_prompt += f"1. wake up and complete the morning routine at <time>, 2. ..."

  new_daily_req = ChatGPT_single_request(daily_req_prompt)
  new_daily_req = new_daily_req.replace('\n', ' ')

  persona.scratch.daily_plan_req = new_daily_req
  refresh_prompt_profile_from_planning(persona, source="revise_identity")


def _long_term_planning(persona, new_day): 
  """
  Formulates the persona's daily long-term plan if it is the start of a new 
  day. This basically has two components: first, we create the wake-up hour, 
  and second, we create the hourly schedule based on it. 
  INPUT
    new_day: Indicates whether the current time signals a "First day",
             "New day", or False (for neither). This is important because we
             create the personas' long term planning on the new day. 
  """
  # We start by creating the wake up hour for the persona. 
  wake_up_hour = generate_wake_up_hour(persona)

  # When it is a new day, we start by creating the daily_req of the persona.
  # Note that the daily_req is a list of strings that describe the persona's
  # day in broad strokes.
  if new_day == "First day": 
    # Bootstrapping the daily plan for the start of then generation:
    # if this is the start of generation (so there is no previous day's 
    # daily requirement, or if we are on a new day, we want to create a new
    # set of daily requirements.
    persona.scratch.daily_req = generate_first_daily_plan(persona, 
                                                          wake_up_hour)
  elif new_day == "New day":
    revise_identity(persona)
    persona.scratch.daily_req = generate_first_daily_plan(persona, wake_up_hour)

  # Hard constraints to enforce realistic daily requirements and avoid LLM plan loss
  if persona.name == "Isabella Rodriguez":
    print(f"=== [日程约束修正] Isabella Rodriguez 日程强制绑定为咖啡店值守 ===")
    persona.scratch.daily_req = [
      "wake up and complete the morning routine at 6:00 am",
      "eat breakfast at 7:00 am",
      "open Hobbs Cafe and work at the counter from 8:00 am to 12:00 pm",
      "have lunch at 12:00 pm",
      "work at the counter of Hobbs Cafe from 1:00 pm to 5:00 pm",
      "work at the counter of Hobbs Cafe from 5:00 pm to 8:00 pm",
      "relax and watch TV from 8:00 pm to 11:00 pm",
      "go to bed at 11:00 pm"
    ]
  elif persona.name == "Klaus Mueller":
    print(f"=== [日程约束修正] Klaus Mueller 日程强制绑定为前往图书馆和在咖啡厅就餐 ===")
    persona.scratch.daily_req = [
      "wake up and complete the morning routine at 7:00 am",
      "eat breakfast at 8:00 am",
      "go to the library at Oak Hill College and write his research paper from 9:00 am to 12:00 pm",
      "have lunch at Hobbs Cafe from 12:00 pm to 1:00 pm",
      "continue writing his research paper at Oak Hill College library from 1:00 pm to 5:00 pm",
      "have dinner at Hobbs Cafe from 5:00 pm to 6:00 pm",
      "relax in his dorm room from 6:00 pm to 11:00 pm",
      "go to bed at 11:00 pm"
    ]

  # Based on the daily_req, we create an hourly schedule for the persona, 
  # which is a list of todo items with a time duration (in minutes) that 
  # add up to 24 hours.
  persona.scratch.f_daily_schedule = generate_hourly_schedule(persona, 
                                                              wake_up_hour)
  persona.scratch.f_daily_schedule_hourly_org = (persona.scratch
                                                   .f_daily_schedule[:])


  # Added March 4 -- adding plan to the memory.
  thought = f"This is {persona.scratch.name}'s plan for {persona.scratch.curr_time.strftime('%A %B %d')}:"
  for i in persona.scratch.daily_req: 
    thought += f" {i},"
  thought = thought[:-1] + "."
  created = persona.scratch.curr_time
  expiration = persona.scratch.curr_time + datetime.timedelta(days=30)
  s, p, o = (persona.scratch.name, "plan", persona.scratch.curr_time.strftime('%A %B %d'))
  keywords = set(["plan"])
  thought_poignancy = 5
  thought_embedding_pair = (thought, get_embedding(thought))
  persona.a_mem.add_thought(created, expiration, s, p, o, 
                            thought, keywords, thought_poignancy, 
                            thought_embedding_pair, None)
  refresh_prompt_profile_from_planning(persona, source="long_term_planning")

  # print("Sleeping for 20 seconds...")
  # time.sleep(10)
  # print("Done sleeping!")



def _determine_action(persona, maze): 
  """
  Creates the next action sequence for the persona. 
  The main goal of this function is to run "add_new_action" on the persona's 
  scratch space, which sets up all the action related variables for the next 
  action. 
  As a part of this, the persona may need to decompose its hourly schedule as 
  needed.   
  INPUT
    persona: Current <Persona> instance whose action we are determining. 
    maze: Current <Maze> instance. 
  """
  def determine_decomp(act_desp, act_dura):
    """
    Given an action description and its duration, we determine whether we need
    to decompose it. If the action is about the agent sleeping, we generally
    do not want to decompose it, so that's what we catch here. 

    INPUT: 
      act_desp: the description of the action (e.g., "sleeping")
      act_dura: the duration of the action in minutes. 
    OUTPUT: 
      a boolean. True if we need to decompose, False otherwise. 
    """
    if "sleep" not in act_desp and "bed" not in act_desp: 
      return True
    elif "sleeping" in act_desp or "asleep" in act_desp or "in bed" in act_desp:
      return False
    elif "sleep" in act_desp or "bed" in act_desp: 
      if act_dura > 60: 
        return False
    return True

  # The goal of this function is to get us the action associated with 
  # <curr_index>. As a part of this, we may need to decompose some large 
  # chunk actions. 
  # Importantly, we try to decompose at least two hours worth of schedule at
  # any given point. 
  curr_index = persona.scratch.get_f_daily_schedule_index()
  curr_index_60 = persona.scratch.get_f_daily_schedule_index(advance=60)

  # * Decompose * 
  # During the first hour of the day, we need to decompose two hours 
  # sequence. We do that here. 
  if curr_index == 0:
    # This portion is invoked if it is the first hour of the day. 
    act_desp, act_dura = persona.scratch.f_daily_schedule[curr_index]
    if act_dura >= 60: 
      # We decompose if the next action is longer than an hour, and fits the
      # criteria described in determine_decomp.
      if determine_decomp(act_desp, act_dura): 
        persona.scratch.f_daily_schedule[curr_index:curr_index+1] = (
                            generate_task_decomp(persona, act_desp, act_dura))
    if curr_index_60 + 1 < len(persona.scratch.f_daily_schedule):
      act_desp, act_dura = persona.scratch.f_daily_schedule[curr_index_60+1]
      if act_dura >= 60: 
        if determine_decomp(act_desp, act_dura): 
          persona.scratch.f_daily_schedule[curr_index_60+1:curr_index_60+2] = (
                            generate_task_decomp(persona, act_desp, act_dura))

  if curr_index_60 < len(persona.scratch.f_daily_schedule):
    # If it is not the first hour of the day, this is always invoked (it is
    # also invoked during the first hour of the day -- to double up so we can
    # decompose two hours in one go). Of course, we need to have something to
    # decompose as well, so we check for that too. 
    if persona.scratch.curr_time.hour < 23:
      # And we don't want to decompose after 11 pm. 
      act_desp, act_dura = persona.scratch.f_daily_schedule[curr_index_60]
      if act_dura >= 60: 
        if determine_decomp(act_desp, act_dura): 
          persona.scratch.f_daily_schedule[curr_index_60:curr_index_60+1] = (
                              generate_task_decomp(persona, act_desp, act_dura))
  # * End of Decompose * 

  # Generate an <Action> instance from the action description and duration. By
  # this point, we assume that all the relevant actions are decomposed and 
  # ready in f_daily_schedule. 


  # 1440
  x_emergency = 0
  for i in persona.scratch.f_daily_schedule: 
    x_emergency += i[1]
  # print ("x_emergency", x_emergency)

  if 1440 - x_emergency > 0: 
    persona.scratch.f_daily_schedule += [["sleeping", 1440 - x_emergency]]
  



  act_desp, act_dura = persona.scratch.f_daily_schedule[curr_index] 

  # Bug fix: adjust duration of the action if we started mid-action (e.g. at start of simulation)
  task_start_min = sum([d for t, d in persona.scratch.f_daily_schedule[:curr_index]])
  today_min_elapsed = persona.scratch.curr_time.hour * 60 + persona.scratch.curr_time.minute
  corrected_act_dura = (task_start_min + act_dura) - today_min_elapsed
  if corrected_act_dura > 0:
    print(f"[修正首个动作时长] 智能体: {persona.scratch.name}, 动作: {act_desp}, 原始计划时长: {act_dura}分钟, 当天已流逝时间: {today_min_elapsed}分钟, 修正后实际执行剩余时长: {corrected_act_dura}分钟")
    act_dura = corrected_act_dura



  # Finding the target location of the action and creating action-related
  # variables.
  act_world = maze.access_tile(persona.scratch.curr_tile)["world"]
  # act_sector = maze.access_tile(persona.scratch.curr_tile)["sector"]
  
  is_coffee_flow = False
  if "serving coffee" in act_desp.lower():
    is_coffee_flow = True
    act_sector = "Hobbs Cafe"
    act_arena = "cafe"
    act_game_object = "cafe customer seating"
    new_address = f"{act_world}:{act_sector}:{act_arena}:{act_game_object}"
    act_pron = "💁"
    act_event = (persona.name, "serve", "coffee to Klaus")
    act_obj_desp = "served with coffee"
    act_obj_pron = "☕"
    act_obj_event = ("cafe customer seating", "has", "served coffee")
  elif "brewing coffee" in act_desp.lower():
    is_coffee_flow = True
    act_sector = "Hobbs Cafe"
    act_arena = "cafe"
    act_game_object = "coffee maker"
    new_address = f"{act_world}:{act_sector}:{act_arena}:{act_game_object}"
    act_pron = "☕"
    act_event = (persona.name, "brew", "coffee")
    act_obj_desp = "brewing coffee"
    act_obj_pron = "♨️"
    act_obj_event = ("coffee maker", "is", "brewing coffee")
  elif "waiting for coffee" in act_desp.lower():
    is_coffee_flow = True
    act_sector = "Hobbs Cafe"
    act_arena = "cafe"
    act_game_object = "cafe customer seating"
    new_address = f"{act_world}:{act_sector}:{act_arena}:{act_game_object}"
    act_pron = "⌛"
    act_event = (persona.name, "waiting for", "coffee")
    act_obj_desp = "empty"
    act_obj_pron = "🍽️"
    act_obj_event = ("cafe customer seating", "is", "empty")
  elif "drinking coffee" in act_desp.lower():
    is_coffee_flow = True
    act_sector = "Hobbs Cafe"
    act_arena = "cafe"
    act_game_object = "cafe customer seating"
    new_address = f"{act_world}:{act_sector}:{act_arena}:{act_game_object}"
    act_pron = "☕"
    act_event = (persona.name, "drink", "coffee")
    act_obj_desp = "empty"
    act_obj_pron = "🍽️"
    act_obj_event = ("cafe customer seating", "is", "empty")

  if not is_coffee_flow:
    act_sector = generate_action_sector(act_desp, persona, maze)
    act_arena = generate_action_arena(act_desp, persona, maze, act_world, act_sector)
    act_address = f"{act_world}:{act_sector}:{act_arena}"
    act_game_object = generate_action_game_object(act_desp, act_address,
                                                  persona, maze)
    new_address = f"{act_world}:{act_sector}:{act_arena}:{act_game_object}"
    act_pron = generate_action_pronunciatio(act_desp, persona)
    act_event = generate_action_event_triple(act_desp, persona)
    # Persona's actions also influence the object states. We set those up here. 
    act_obj_desp = generate_act_obj_desc(act_game_object, act_desp, persona)
    act_obj_pron = generate_action_pronunciatio(act_obj_desp, persona)
    act_obj_event = generate_act_obj_event_triple(act_game_object, 
                                                  act_obj_desp, persona)

  # Adding the action to persona's queue. 
  persona.scratch.add_new_action(new_address, 
                                 int(act_dura), 
                                 act_desp, 
                                 act_pron, 
                                 act_event,
                                 None,
                                 None,
                                 None,
                                 None,
                                 None,
                                 act_obj_desp, 
                                 act_obj_pron, 
                                 act_obj_event)


def _choose_retrieved(persona, retrieved): 
  """
  Retrieved elements have multiple core "curr_events". We need to choose one
  event to which we are going to react to. We pick that event here. 
  INPUT
    persona: Current <Persona> instance whose action we are determining. 
    retrieved: A dictionary of <ConceptNode> that were retrieved from the 
               the persona's associative memory. This dictionary takes the
               following form: 
               dictionary[event.description] = 
                 {["curr_event"] = <ConceptNode>, 
                  ["events"] = [<ConceptNode>, ...], 
                  ["thoughts"] = [<ConceptNode>, ...] }
  """
  # Once we are done with the reflection, we might want to build a more  
  # complex structure here.
  
  # We do not want to take self events... for now 
  copy_retrieved = retrieved.copy()
  for event_desc, rel_ctx in copy_retrieved.items(): 
    curr_event = rel_ctx["curr_event"]
    if curr_event.subject == persona.name: 
      del retrieved[event_desc]

  # Always choose persona first.
  priority = []
  for event_desc, rel_ctx in retrieved.items(): 
    curr_event = rel_ctx["curr_event"]
    if (":" not in curr_event.subject 
        and curr_event.subject != persona.name): 
      priority += [rel_ctx]
  if priority: 
    return random.choice(priority)

  # Skip idle. 
  for event_desc, rel_ctx in retrieved.items(): 
    curr_event = rel_ctx["curr_event"]
    if "is idle" not in event_desc: 
      priority += [rel_ctx]
  if priority: 
    return random.choice(priority)
  return None


def _decrement_chatting_with_buffer(persona):
  """
  Decrease chat cooldown counters without allowing negative values to accumulate.
  """
  stale_names = []
  for persona_name, buffer_count in persona.scratch.chatting_with_buffer.items():
    if persona_name == persona.scratch.chatting_with:
      continue
    next_count = max(0, int(buffer_count) - 1)
    persona.scratch.chatting_with_buffer[persona_name] = next_count
    if next_count == 0:
      stale_names += [persona_name]
  for persona_name in stale_names:
    del persona.scratch.chatting_with_buffer[persona_name]


def _should_react(persona, retrieved, personas): 
  """
  Determines what form of reaction the persona should exihibit given the 
  retrieved values. 
  INPUT
    persona: Current <Persona> instance whose action we are determining. 
    retrieved: A dictionary of <ConceptNode> that were retrieved from the 
               the persona's associative memory. This dictionary takes the
               following form: 
               dictionary[event.description] = 
                 {["curr_event"] = <ConceptNode>, 
                  ["events"] = [<ConceptNode>, ...], 
                  ["thoughts"] = [<ConceptNode>, ...] }
    personas: A dictionary that contains all persona names as keys, and the 
              <Persona> instance as values. 
  """
  def lets_talk(init_persona, target_persona, retrieved):
    hard_blocked, hard_reasons = social_hard_block(init_persona, target_persona)
    score_detail = compute_social_opportunity_score(init_persona, target_persona, retrieved)
    log_social_dialogue(
      init_persona,
      "trigger",
      "chat_candidate",
      target_name=target_persona.name,
      payload={
        "blocked": hard_blocked,
        "hard_block_reasons": hard_reasons,
        "score": score_detail,
      },
    )
    log_social_decision(
      init_persona,
      target_persona.name,
      "chat_candidate",
      {
        "blocked": hard_blocked,
        "hard_block_reasons": hard_reasons,
        "score": score_detail,
      },
    )
    if hard_blocked:
      log_social_dialogue(
        init_persona,
        "trigger",
        "chat_rejected_hard_block",
        target_name=target_persona.name,
        payload={"reasons": hard_reasons},
      )
      return False
    if score_detail["total"] < minimum_social_chat_score(init_persona):
      log_social_dialogue(
        init_persona,
        "trigger",
        "chat_rejected_low_score",
        target_name=target_persona.name,
        payload={"score": score_detail},
      )
      log_social_decision(
        init_persona,
        target_persona.name,
        "chat_rejected_low_score",
        {
          "score": score_detail,
        },
      )
      return False

    if should_auto_initiate_social_chat(score_detail):
      log_social_dialogue(
        init_persona,
        "trigger",
        "chat_auto_initiate",
        target_name=target_persona.name,
        payload={
          "score": score_detail,
          "reason": "high_opportunity_score",
        },
      )
      log_social_decision(
        init_persona,
        target_persona.name,
        "chat_auto_initiate",
        {
          "score": score_detail,
          "reason": "high_opportunity_score",
        },
      )
      return True

    llm_wants_to_talk = generate_decide_to_talk(init_persona, target_persona, retrieved)
    log_social_dialogue(
      init_persona,
      "trigger",
      "chat_llm_decision",
      target_name=target_persona.name,
      payload={
        "score": score_detail,
        "llm_initiate": bool(llm_wants_to_talk),
      },
    )
    log_social_decision(
      init_persona,
      target_persona.name,
      "chat_llm_decision",
      {
        "score": score_detail,
        "llm_initiate": bool(llm_wants_to_talk),
      },
    )
    if llm_wants_to_talk: 
      return True

    return False

  def lets_react(init_persona, target_persona, retrieved): 
    if (not target_persona.scratch.act_address 
        or not target_persona.scratch.act_description
        or not init_persona.scratch.act_address
        or not init_persona.scratch.act_description): 
      return False

    if ("sleeping" in target_persona.scratch.act_description 
        or "sleeping" in init_persona.scratch.act_description): 
      return False

    # return False
    if init_persona.scratch.curr_time.hour == 23: 
      return False

    if "waiting" in target_persona.scratch.act_description: 
      return False
    if init_persona.scratch.planned_path == []:
      return False

    if (init_persona.scratch.act_address 
        != target_persona.scratch.act_address): 
      return False

    react_mode = generate_decide_to_react(init_persona, 
                                          target_persona, retrieved)

    if react_mode == "1": 
      wait_until = ((target_persona.scratch.act_start_time 
        + datetime.timedelta(minutes=target_persona.scratch.act_duration - 1))
        .strftime("%B %d, %Y, %H:%M:%S"))
      return f"wait: {wait_until}"
    elif react_mode == "2":
      return False
      return "do other things"
    else:
      return False #"keep" 

  # If the persona is chatting right now, default to no reaction 
  if persona.scratch.chatting_with: 
    return False
  act_address = getattr(persona.scratch, "act_address", None) or ""
  if "<waiting>" in act_address: 
    return False

  # Recall that retrieved takes the following form: 
  # dictionary {["curr_event"] = <ConceptNode>, 
  #             ["events"] = [<ConceptNode>, ...], 
  #             ["thoughts"] = [<ConceptNode>, ...]}
  curr_event = retrieved["curr_event"]

  if ":" not in curr_event.subject: 
    # this is a persona event. 
    if lets_talk(persona, personas[curr_event.subject], retrieved):
      return f"chat with {curr_event.subject}"
    react_mode = lets_react(persona, personas[curr_event.subject], 
                            retrieved)
    return react_mode
  return False


def _create_react(persona, inserted_act, inserted_act_dur,
                  act_address, act_event, chatting_with, chat, chatting_with_buffer,
                  chatting_end_time, 
                  act_pronunciatio, act_obj_description, act_obj_pronunciatio, 
                  act_obj_event, act_start_time=None): 
  p = persona 
  hourly_schedule = getattr(p.scratch, "f_daily_schedule_hourly_org", None) or []
  active_schedule = getattr(p.scratch, "f_daily_schedule", None) or []

  if not hourly_schedule or not active_schedule:
    append_debug_log(
      "decision_stability.jsonl",
      {
        "persona": getattr(p, "name", None),
        "event": "react_schedule_fallback",
        "curr_step": getattr(p.scratch, "curr_step", None),
        "reason": "missing_schedule",
        "hourly_schedule_len": len(hourly_schedule),
        "active_schedule_len": len(active_schedule),
        "inserted_act": inserted_act,
      }
    )
    p.scratch.add_new_action(act_address,
                             inserted_act_dur,
                             inserted_act,
                             act_pronunciatio,
                             act_event,
                             None,
                             chatting_with,
                             chat,
                             chatting_with_buffer,
                             chatting_end_time,
                             act_obj_description,
                             act_obj_pronunciatio,
                             act_obj_event,
                             act_start_time)
    return

  hourly_index = p.scratch.get_f_daily_schedule_hourly_org_index()
  hourly_index = max(0, min(hourly_index, len(hourly_schedule) - 1))
  next_hourly_index = min(hourly_index + 1, len(hourly_schedule) - 1)
  min_sum = 0
  for i in range(hourly_index): 
    min_sum += hourly_schedule[i][1]
  start_hour = int (min_sum/60)

  current_block_minutes = hourly_schedule[hourly_index][1]
  next_block_minutes = hourly_schedule[next_hourly_index][1] if next_hourly_index != hourly_index else 0
  if current_block_minutes >= 120:
    end_hour = start_hour + current_block_minutes / 60
  elif next_block_minutes > 0:
    end_hour = start_hour + ((current_block_minutes + next_block_minutes) / 60)

  else: 
    end_hour = start_hour + 2
  end_hour = int(end_hour)

  dur_sum = 0
  count = 0 
  start_index = None
  end_index = None
  for act, dur in p.scratch.f_daily_schedule: 
    if dur_sum >= start_hour * 60 and start_index == None:
      start_index = count
    if dur_sum >= end_hour * 60 and end_index == None: 
      end_index = count
    dur_sum += dur
    count += 1

  if start_index is None:
    start_index = max(0, len(p.scratch.f_daily_schedule) - 1)
  if end_index is None:
    end_index = len(p.scratch.f_daily_schedule)

  ret = generate_new_decomp_schedule(p, inserted_act, inserted_act_dur, 
                                       start_hour, end_hour)
  p.scratch.f_daily_schedule[start_index:end_index] = ret
  p.scratch.add_new_action(act_address,
                           inserted_act_dur,
                           inserted_act,
                           act_pronunciatio,
                           act_event,
                           None,
                           chatting_with,
                           chat,
                           chatting_with_buffer,
                           chatting_end_time,
                           act_obj_description,
                           act_obj_pronunciatio,
                           act_obj_event,
                           act_start_time)


def inject_coffee_flow(p, role, chatting_end_time):
  # 1. Calculate the minute of the day when the chat ends
  chat_end_min = chatting_end_time.hour * 60 + chatting_end_time.minute
  
  # 2. Rebuild f_daily_schedule
  new_schedule = []
  elapsed = 0
  rest_schedule = []
  
  for task, dur in p.scratch.f_daily_schedule:
    if elapsed + dur <= chat_end_min:
      new_schedule.append([task, dur])
      elapsed += dur
    elif elapsed < chat_end_min and elapsed + dur > chat_end_min:
      past_dur = chat_end_min - elapsed
      new_schedule.append([task, past_dur])
      
      future_dur = (elapsed + dur) - chat_end_min
      rest_schedule.append([task, future_dur])
      elapsed += dur
    else:
      rest_schedule.append([task, dur])
      elapsed += dur
      
  # 3. Define the custom workflow blocks
  workflow_blocks = []
  if role == "barista":
    workflow_blocks = [
      ["brewing coffee at the coffee maker", 5],
      ["serving coffee to Klaus", 2]
    ]
  elif role == "customer":
    workflow_blocks = [
      ["waiting for coffee to be served", 7],
      ["drinking coffee", 15]
    ]
    
  workflow_duration = sum(b[1] for b in workflow_blocks)
  new_schedule.extend(workflow_blocks)
  
  # 4. Append the rest of the schedule, adjusting durations
  remaining_to_subtract = workflow_duration
  for task, dur in rest_schedule:
    if remaining_to_subtract > 0:
      if dur > remaining_to_subtract:
        new_schedule.append([task, dur - remaining_to_subtract])
        remaining_to_subtract = 0
      else:
        remaining_to_subtract -= dur
    else:
      new_schedule.append([task, dur])
      
  total_sum = sum(b[1] for b in new_schedule)
  if total_sum < 1440:
    new_schedule.append(["sleeping", 1440 - total_sum])
  elif total_sum > 1440:
    new_schedule[-1][1] -= (total_sum - 1440)
    
  p.scratch.f_daily_schedule = new_schedule
  print(f"[注入成功] {p.name} 的日程表已成功注入咖啡协同动作，新日程总时长: {sum(b[1] for b in p.scratch.f_daily_schedule)} 分钟")


def _chat_react(maze, persona, focused_event, reaction_mode, personas):
  # There are two personas -- the persona who is initiating the conversation
  # and the persona who is the target. We get the persona instances here. 
  init_persona = persona
  target_persona = personas[reaction_mode[9:].strip()]
  curr_personas = [init_persona, target_persona]

  # In the refactored Chat Skill Pack architecture, we perform lazy execution.
  # We do not generate dialogue at the planning stage. Instead, we use a placeholder action
  # and a default duration (10 minutes). The dialogue is generated dynamically upon arrival.
  inserted_act_dur = 10

  act_start_time = target_persona.scratch.act_start_time

  curr_time = target_persona.scratch.curr_time
  if curr_time.second != 0: 
    temp_curr_time = curr_time + datetime.timedelta(seconds=60 - curr_time.second)
    chatting_end_time = temp_curr_time + datetime.timedelta(minutes=inserted_act_dur)
  else: 
    chatting_end_time = curr_time + datetime.timedelta(minutes=inserted_act_dur)
  dialogue_id = build_dialogue_id(init_persona, target_persona)

  for role, p in [("init", init_persona), ("target", target_persona)]: 
    if role == "init": 
      inserted_act = f"having a conversation with {target_persona.name}"
      act_address = f"<persona> {target_persona.name}"
      act_event = (p.name, "chat with", target_persona.name)
      chatting_with = target_persona.name
      chatting_with_buffer = {}
      score_detail = compute_social_opportunity_score(p, target_persona, focused_event)
      chatting_with_buffer[target_persona.name] = compute_social_cooldown(p, target_persona, focused_event, score_detail)
    elif role == "target": 
      inserted_act = f"having a conversation with {init_persona.name}"
      act_address = f"<persona> {init_persona.name}"
      act_event = (p.name, "chat with", init_persona.name)
      chatting_with = init_persona.name
      chatting_with_buffer = {}
      score_detail = compute_social_opportunity_score(p, init_persona, focused_event)
      chatting_with_buffer[init_persona.name] = compute_social_cooldown(p, init_persona, focused_event, score_detail)

    act_pronunciatio = "💬" 
    act_obj_description = None
    act_obj_pronunciatio = None
    act_obj_event = (None, None, None)

    _create_react(p, inserted_act, inserted_act_dur,
      act_address, act_event, chatting_with, None, chatting_with_buffer, chatting_end_time,
      act_pronunciatio, act_obj_description, act_obj_pronunciatio, 
      act_obj_event, act_start_time)
    set_social_dialogue_state(p, dialogue_id, partner_name=chatting_with, role=role)
    if hasattr(p.scratch, "begin_complex_skill"):
      p.scratch.begin_complex_skill(
        "chat",
        skill_id=dialogue_id,
        phase="pathing",
        owner=role,
        target=chatting_with,
        metadata={
          "dialogue_id": dialogue_id,
          "chatting_end_time": chatting_end_time.strftime("%B %d, %Y, %H:%M:%S"),
        },
      )
    log_social_decision(
      p,
      chatting_with,
      "chat_react_enqueued",
      {
        "cooldown": chatting_with_buffer.get(chatting_with),
        "inserted_act": inserted_act,
        "chatting_end_time": chatting_end_time,
      },
    )
    log_social_dialogue(
      p,
      "schedule",
      "chat_react_enqueued",
      target_name=chatting_with,
      dialogue_id=dialogue_id,
      payload={
        "cooldown": chatting_with_buffer.get(chatting_with),
        "inserted_act": inserted_act,
        "chatting_end_time": chatting_end_time,
      },
    )


def _wait_react(persona, reaction_mode): 
  p = persona

  inserted_act = f'waiting to start {p.scratch.act_description.split("(")[-1][:-1]}'
  end_time = datetime.datetime.strptime(reaction_mode[6:].strip(), "%B %d, %Y, %H:%M:%S")
  inserted_act_dur = (end_time.minute + end_time.hour * 60) - (p.scratch.curr_time.minute + p.scratch.curr_time.hour * 60) + 1

  act_address = f"<waiting> {p.scratch.curr_tile[0]} {p.scratch.curr_tile[1]}"
  act_event = (p.name, "waiting to start", p.scratch.act_description.split("(")[-1][:-1])
  chatting_with = None
  chat = None
  chatting_with_buffer = None
  chatting_end_time = None

  act_pronunciatio = "⌛" 
  act_obj_description = None
  act_obj_pronunciatio = None
  act_obj_event = (None, None, None)

  _create_react(p, inserted_act, inserted_act_dur,
    act_address, act_event, chatting_with, chat, chatting_with_buffer, chatting_end_time,
    act_pronunciatio, act_obj_description, act_obj_pronunciatio, act_obj_event)


def decide_survival_action(persona, maze):
  import json
  # Get all objects the persona knows about
  objs = set()
  for w in persona.s_mem.tree:
    for s in persona.s_mem.tree[w]:
      for a in persona.s_mem.tree[w][s]:
        for obj in persona.s_mem.tree[w][s][a]:
          objs.add(obj)
  objs_list = list(objs)

  # Query environment micro-states and cooperative details
  object_states = []
  cooperative_events = []
  
  for obj in objs_list:
    address = persona.s_mem.find_nearest_object(obj)
    if address and address in maze.address_tiles:
      tiles = list(maze.address_tiles[address])
      events_on_obj = []
      for tile in tiles:
        tile_details = maze.access_tile(tile)
        if tile_details and tile_details["events"]:
          for ev in tile_details["events"]:
            ev_str = str(ev)
            events_on_obj.append(ev_str)
            if any(kw in ev_str.lower() for kw in ["waiting", "serve", "served"]):
              cooperative_events.append(f"{ev_str} (at {obj})")
      if events_on_obj:
        object_states.append(f"{obj} (current state: {', '.join(events_on_obj)})")
      else:
        object_states.append(f"{obj} (idle/normal)")
    else:
      object_states.append(f"{obj} (normal)")

  # Compile Temporal Context
  curr_time_str = persona.scratch.curr_time.strftime("%A %B %d, %Y, %I:%M %p") if persona.scratch.curr_time else "Unknown"
  act_desc = persona.scratch.act_description if persona.scratch.act_description else "None"
  act_dur = persona.scratch.act_duration if persona.scratch.act_duration else 0
  temporal_context = f"- Current Time: {curr_time_str}\n- Active Scheduled Action: '{act_desc}' (Planned duration remaining: {act_dur} minutes)"

  # Compile Physiological Rules
  physiological_rules = (
      "- Consuming food (Consume action) restores +40.0 Satiety and +5.0 Health, and consumes 1 food item from inventory.\n"
      "- Gathering food (Gather action) from resources (like apple tree, refrigerator, stove, and cafe counter) adds items to inventory.\n"
      "- Resting (Rest action) restores Stamina over time: sleeping restores about +0.15 per step, and resting restores about +0.08 per step.\n"
      "- Satiety decays by about -0.08 per step during normal activity, and by about -0.04 per step while sleeping.\n"
      "- If Satiety reaches 0.0, Health decays by -0.05 per step."
  )

  # Compile Cooperative Context
  cooperative_context = ""
  if cooperative_events:
    cooperative_context += "Active cooperative/social events nearby:\n" + "\n".join([f"- {ev}" for ev in cooperative_events])
  else:
    cooperative_context += "No special cooperative tasks or wait states are active nearby."

  curr_sector = maze.get_tile_path(persona.scratch.curr_tile, "sector").lower() if (persona.scratch.curr_tile and maze.get_tile_path(persona.scratch.curr_tile, "sector")) else ""
  is_worker = any(job in persona.scratch.learned.lower() for job in ["owner", "barista", "employee", "worker", "staff"]) and curr_sector in persona.scratch.learned.lower()
  if is_worker:
    cooperative_context += f"\n- NOTE: You are a staff/owner of the current area ({curr_sector}). You do not need to wait for others to serve you food/drink; you have direct access to resources and can gather or prepare food yourself."

  # Call GPT to decide survival action
  decision = run_gpt_prompt_survival_decision(
      persona, 
      object_states, 
      temporal_context=temporal_context, 
      physiological_rules=physiological_rules, 
      cooperative_context=cooperative_context
  )
  action = decision.get("action", "Idle")
  target = decision.get("target", "none")
  reasoning = decision.get("reasoning", "")
  act_desp = decision.get("detail", "")
  action, target, act_desp, reasoning = _autofill_consume_target(
    persona,
    action,
    target,
    act_desp,
    reasoning,
  )
  action, target, act_desp, reasoning = _autofill_place_target(
    persona,
    maze,
    action,
    target,
    act_desp,
    reasoning,
  )
  print(f"[{persona.name}] 经过LLM生存分析做出决策: Action={action}, Target={target}, 原因={reasoning}")

  if action == "Idle" or target == "none":
    # Idle action
    persona.scratch.act_address = f"{persona.scratch.living_area}"
    persona.scratch.act_description = act_desp or "idling to conserve energy"
    persona.scratch.act_duration = 10
    persona.scratch.act_start_time = persona.scratch.curr_time
    persona.scratch.act_pronunciatio = "💤"
    persona.scratch.act_event = (persona.name, "idle", "none")
    persona.scratch.act_command = build_action_command("idle", "none", source="survival_direct", raw_action="idle", detail=persona.scratch.act_description)
    persona.scratch.act_path_set = False
    return persona.scratch.act_address

  # Resolve object address
  address = persona.s_mem.find_nearest_object(target)
  if not address:
    # Fallback to living area
    address = f"{persona.scratch.living_area}"

  if action == "Consume":
    # Check if target is in inventory (case-insensitive)
    item_key = target.strip().lower()
    in_inv = False
    for k in persona.scratch.inventory:
      if k.strip().lower() == item_key and persona.scratch.inventory[k] > 0:
        in_inv = True
        break
    
    if not in_inv:
      print(f"[{persona.name}] 背包中没有 {target}！修改动作为 Gather 从环境获取。")
      action = "Gather"
      # Route cafe food acquisition to the executable counter resource.
      if "behind the cafe counter" in objs_list or "cafe customer seating" in objs_list:
        target = "cafe counter"
      else:
        target = "refrigerator" if "refrigerator" in objs_list else "apple tree"
      address = persona.s_mem.find_nearest_object(target) or address
    else:
      address = _current_tile_wait_address(persona)


  if action == "Gather":
    persona.scratch.act_address = address
    persona.scratch.act_description = f"gathering from {target}"
    persona.scratch.act_duration = 15
    persona.scratch.act_start_time = persona.scratch.curr_time
    persona.scratch.act_pronunciatio = "🍎"
    persona.scratch.act_event = (persona.name, "gather", target)
    persona.scratch.act_command = build_action_command("gather", target, source="survival_direct", raw_action="gather")
    persona.scratch.act_obj_description = f"being harvested by {persona.scratch.first_name}"
    persona.scratch.act_obj_pronunciatio = "🍎"
    persona.scratch.act_obj_event = (target, "harvested_by", persona.name)
    persona.scratch.act_path_set = False

  elif action == "Consume":
    persona.scratch.act_address = address
    persona.scratch.act_description = f"consuming {target}"
    persona.scratch.act_duration = 5
    persona.scratch.act_start_time = persona.scratch.curr_time
    persona.scratch.act_pronunciatio = "🍴"
    persona.scratch.act_event = (persona.name, "consume", target)
    persona.scratch.act_command = build_action_command("consume", target, source="survival_direct", raw_action="consume")
    persona.scratch.act_obj_description = f"being eaten by {persona.scratch.first_name}"
    persona.scratch.act_obj_pronunciatio = "🍴"
    persona.scratch.act_obj_event = (target, "consumed_by", persona.name)
    persona.scratch.act_path_set = False

  elif action == "Rest":
    persona.scratch.act_address = address
    persona.scratch.act_description = f"resting at {target}"
    persona.scratch.act_duration = 30
    persona.scratch.act_start_time = persona.scratch.curr_time
    persona.scratch.act_pronunciatio = "🛌"
    persona.scratch.act_event = (persona.name, "rest", target)
    persona.scratch.act_command = build_action_command("rest", target, source="survival_direct", raw_action="rest")
    persona.scratch.act_obj_description = f"being rested on by {persona.scratch.first_name}"
    persona.scratch.act_obj_pronunciatio = "🛌"
    persona.scratch.act_obj_event = (target, "rested_on_by", persona.name)
    persona.scratch.act_path_set = False

  return persona.scratch.act_address


def decide_demand_action(persona, maze, personas=None):
  import json
  decision_started_at = time.perf_counter()
  phase_started_at = decision_started_at
  timings_ms = {}
  if personas is not None:
    persona.runtime_known_personas = personas

  # Get all objects the persona knows about
  objs = set()
  for w in persona.s_mem.tree:
    for s in persona.s_mem.tree[w]:
      for a in persona.s_mem.tree[w][s]:
        for obj in persona.s_mem.tree[w][s][a]:
          objs.add(obj)
  objs_list = list(objs)
  world_state = getattr(persona, "world_resource_state", None)
  gatherable_food_targets = []
  for obj in objs_list:
    normalized_obj = normalize_food_source_target(obj)
    if not is_valid_gather_food_source(normalized_obj):
      continue
    if not world_state or world_state.has_available_target(normalized_obj):
      gatherable_food_targets.append(normalized_obj)
  gatherable_food_targets = list(dict.fromkeys(gatherable_food_targets))

  # Query environment micro-states and cooperative details
  object_states = []
  cooperative_events = []
  
  for obj in objs_list:
    address = persona.s_mem.find_nearest_object(obj)
    resource_state = _describe_resource_state(persona, obj, address=address)
    if address and address in maze.address_tiles:
      tiles = list(maze.address_tiles[address])
      events_on_obj = []
      for tile in tiles:
        tile_details = maze.access_tile(tile)
        if tile_details and tile_details["events"]:
          for ev in tile_details["events"]:
            ev_str = str(ev)
            events_on_obj.append(ev_str)
            if any(kw in ev_str.lower() for kw in ["waiting", "serve", "served"]):
              cooperative_events.append(f"{ev_str} (at {obj})")
      if events_on_obj:
        object_states.append(f"{obj} (current state: {', '.join(events_on_obj)}; {resource_state})")
      else:
        object_states.append(f"{obj} (idle/normal; {resource_state})")
    else:
      object_states.append(f"{obj} ({resource_state})")

  # Compile Temporal Context
  curr_time_str = persona.scratch.curr_time.strftime("%A %B %d, %Y, %I:%M %p") if persona.scratch.curr_time else "Unknown"
  temporal_context = f"- Current Time: {curr_time_str}"
  status_summary = _build_homeostasis_status_summary(persona)

  # Compile world facts and execution constraints without prescribing a motive.
  rules_list = [
      "- Consuming food (Consume action) restores +40.0 Satiety and +5.0 Health, and consumes 1 food item from inventory.",
      "- Gathering food (Gather action) from resources (like apple tree, refrigerator, stove, and cafe counter) adds items to inventory.",
      "- Resting (Rest action) restores Stamina over time: sleeping restores about +0.15 per step, and resting restores about +0.08 per step.",
      "- Socializing (Socialize action) provides only a tiny mood lift (+1.0 Mood) and a little comfort, but short chats should not dramatically change your emotional state.",
      "- Normal activities decay Satiety by -0.08 per step, and sleeping decays Satiety by -0.04 per step.",
      "- Normal activities decay Stamina by -0.04 per step, and walking/pathing decays Stamina by -0.07 per step.",
      "- Sleeping restores Stamina by +0.15 per step, and resting restores Stamina by +0.08 per step.",
      "- Switch Cost: Changing tasks/actions in under 15 minutes consumes a high penalty of -5.0 Stamina.",
      "- If Satiety reaches 0.0, Health decays by -0.05 per step."
  ]

  # Add only factual availability and physical consequence notes.
  if persona.scratch.satiety < 40.0:
    rules_list.insert(0, f"- PHYSICAL WARNING: Your Satiety ({persona.scratch.satiety:.1f}) is low! If Satiety drops to 0.0, the physical world engine will degrade your Health by -0.05 per step until you die.")
    has_food = False
    for k, v in persona.scratch.inventory.items():
      if v > 0:
        rules_list.insert(0, f"- AVAILABLE RESOURCE: You currently have food ({k}) in your inventory, so 'Consume' can target '{k}'.")
        has_food = True
        break
    if not has_food:
      rules_list.insert(0, "- EXECUTION CONSTRAINT: Your inventory is empty, so 'Consume' is not currently executable until food is acquired.")
  if not any(v > 0 for v in persona.scratch.inventory.values()):
    if world_state and not any(t in gatherable_food_targets for t in ["refrigerator", "stove", "cafe counter"]) and "apple tree" in gatherable_food_targets:
      rules_list.insert(0, "- WORLD FACT: Known town food sources are depleted or unavailable right now; the apple tree is still available.")
  
  if persona.scratch.stamina < 40.0:
    rules_list.insert(0, f"- PHYSICAL WARNING: Your Stamina ({persona.scratch.stamina:.1f}) is low! Changing tasks quickly costs -5.0 Stamina, while normal activities decay it by about -0.04 per step and walking/pathing decays it by about -0.07 per step.")
    rules_list.insert(0, "- AVAILABLE RESOURCE: Rest can target a 'bed' or 'sofa' when either is reachable.")

  physiological_rules = "\n".join(rules_list)

  # Compile Cooperative Context
  cooperative_context = ""
  if cooperative_events:
    cooperative_context += "Active cooperative/social events nearby:\n" + "\n".join([f"- {ev}" for ev in cooperative_events])
  else:
    cooperative_context += "No special cooperative tasks or wait states are active nearby."

  curr_sector = maze.get_tile_path(persona.scratch.curr_tile, "sector").lower() if (persona.scratch.curr_tile and maze.get_tile_path(persona.scratch.curr_tile, "sector")) else ""
  is_worker = any(job in persona.scratch.learned.lower() for job in ["owner", "barista", "employee", "worker", "staff"]) and curr_sector in persona.scratch.learned.lower()
  if is_worker:
    cooperative_context += f"\n- NOTE: You are a staff/owner of the current area ({curr_sector}). You do not need to wait for others to serve you food/drink; you have direct access to resources and can gather or prepare food yourself."

  # Capture last action context
  context_build_started_at = phase_started_at
  last_action_desc = getattr(persona.scratch, 'last_action_desc', "None")
  phase_started_at = time.perf_counter()
  active_signature = persona.scratch.get_active_decision_signature() or {}
  intent_family = infer_memory_focus(persona, active_signature)
  intent_memories = retrieve_intent_memories(
    persona,
    intent_family,
    action_signature=active_signature,
    n_count=5,
  )
  intent_memory_summary = summarize_intent_memories(intent_family, intent_memories)
  timings_ms["intent_memory_retrieval"] = _elapsed_ms(phase_started_at)
  timings_ms["context_build"] = _elapsed_ms(context_build_started_at)
  static_resource_context_text = _build_static_resource_context_text(persona, maze)

  decision_id = _build_decision_id(persona)
  admin_override_instruction = _get_admin_override_instruction(persona)
  if admin_override_instruction:
    override_line = (
      f"Active administrator override: {admin_override_instruction}. "
      "This external instruction has highest priority for the next replan unless blocked by hard physical constraints."
    )
    physiological_rules = f"{override_line}\n{physiological_rules}"
  thinking_text, decision, translation_convergence_hint, used_joint_decision, decision_timing_meta, decision_cache_signature = _run_decision_pipeline(
    persona,
    object_states,
    temporal_context,
    status_summary,
    physiological_rules,
    cooperative_context,
    last_action_desc,
    intent_memory_summary,
    admin_override_instruction=admin_override_instruction,
    intent_family=intent_family,
    decision_id=decision_id,
    static_resource_context_text=static_resource_context_text,
  )
  timings_ms["decision_cache_lookup"] = float(decision_timing_meta.get("decision_cache_lookup", 0.0) or 0.0)
  timings_ms["decision_cache_hit"] = float(decision_timing_meta.get("decision_cache_hit", 0.0) or 0.0)
  timings_ms["joint_decision"] = float(decision_timing_meta.get("joint_decision", 0.0) or 0.0)
  timings_ms["demand_thinking"] = float(decision_timing_meta.get("demand_thinking", 0.0) or 0.0)
  timings_ms["action_translation"] = float(decision_timing_meta.get("action_translation", 0.0) or 0.0)
  print(f"[{persona.name}] 决策输出: '{thinking_text}' (joint={used_joint_decision})")

  action = decision.get("action", "Idle")
  if action is None: action = "Idle"
  action = str(action)

  target = decision.get("target", "none")
  if target is None: target = "none"
  target = str(target)

  act_desp = decision.get("detail", "idling")
  if act_desp is None: act_desp = "idling"
  act_desp = str(act_desp)

  default_dura = 2 if action == "Consume" else 10
  act_dura = decision.get("duration", default_dura)
  if act_dura is None: act_dura = default_dura
  try:
    act_dura = int(act_dura)
  except:
    act_dura = default_dura

  reasoning = decision.get("reasoning", "")
  if reasoning is None: reasoning = ""
  reasoning = str(reasoning)
  action, target, act_desp, reasoning = _autofill_consume_target(
    persona,
    action,
    target,
    act_desp,
    reasoning,
  )
  action, target, act_desp, reasoning = _autofill_rest_target(
    persona,
    action,
    target,
    act_desp,
    reasoning,
  )
  action, target, act_desp, reasoning = _autofill_place_target(
    persona,
    maze,
    action,
    target,
    act_desp,
    reasoning,
  )
  action, target, act_desp, reasoning, collective_social_reroute = _coerce_collective_social_hangout(
    action,
    target,
    act_desp,
    reasoning,
  )
  action, target, act_desp, reasoning, explicit_persona_chat_reroute = _coerce_explicit_persona_chat(
    action,
    target,
    act_desp,
    reasoning,
    personas=personas,
  )
  minimal_filter_summary = _build_minimal_filter_summary(persona, object_states, decision_timing_meta=decision_timing_meta)
  motive_debug = persona.scratch.get_motive_debug_snapshot() if hasattr(persona.scratch, "get_motive_debug_snapshot") else {}
  append_debug_log(
    "training_dataset/decision_training_prep.jsonl",
    normalize_training_log_record(
      {
        "event": "decision_logged",
        "decision_id": decision_id,
        "persona": persona.name,
        "curr_step": getattr(persona.scratch, "curr_step", None),
        "prompt_kind": "joint_decision" if used_joint_decision else "action_translation",
        "final_prompt": None,
        "decision": decision,
        "collective_social_reroute": bool(collective_social_reroute),
        "explicit_persona_chat_reroute": bool(explicit_persona_chat_reroute),
        "constraint_hit": bool(decision_timing_meta.get("constraint_hits", 0)),
        "retry_reason": decision_timing_meta.get("last_retry_reason", ""),
        "execution_outcome": "decision_selected",
        "minimal_filter_enabled": bool(minimal_filter_summary.get("enabled")),
        "minimal_filter_applied": bool(minimal_filter_summary.get("applied")),
        "minimal_filter_summary": minimal_filter_summary,
      }
    ),
  )
  has_food_inventory = any(v > 0 for v in persona.scratch.inventory.values())
  normalized_target = normalize_food_source_target(target)
  if action.lower() == "consume" and not has_food_inventory and is_valid_gather_food_source(normalized_target):
    append_debug_log(
      "translation_verify.jsonl",
      {
        "persona": persona.name,
        "event": "coerce_consume_source_to_gather",
        "original_action": action,
        "original_target": target,
        "coerced_target": normalized_target,
        "reason": "inventory_empty_food_source_target",
      }
    )
    action = "Gather"
    target = normalized_target
    if normalized_target == "refrigerator":
      act_desp = "opening the refrigerator to gather food items"
    elif normalized_target == "stove":
      act_desp = "preparing food from the stove"
    elif normalized_target == "cafe counter":
      act_desp = "getting prepared food from the cafe counter"
    elif normalized_target == "apple tree":
      act_desp = "gathering apples from the apple tree"

  if action.lower() == "gather":
    normalized_target = normalize_food_source_target(target)
    if persona.scratch.satiety < 40.0 and not has_food_inventory:
      if not is_valid_gather_food_source(normalized_target):
        fallback_target = None
        for candidate in ["refrigerator", "stove", "cafe counter", "apple tree"]:
          if candidate in gatherable_food_targets:
            fallback_target = candidate
            break
        if not fallback_target and gatherable_food_targets:
          fallback_target = normalize_food_source_target(gatherable_food_targets[0])
        if fallback_target:
          append_debug_log(
            "translation_verify.jsonl",
            {
              "persona": persona.name,
              "event": "retarget_invalid_food_source",
              "original_target": target,
              "fallback_target": fallback_target,
              "valid_sources": gatherable_food_targets,
            }
          )
          target = fallback_target
          if "refrigerator" in fallback_target:
            act_desp = "opening the refrigerator to gather food items"
          elif "stove" in fallback_target:
            act_desp = "preparing food from the stove"
          elif "cafe counter" in fallback_target:
            act_desp = "getting prepared food from the cafe counter"
          elif "apple tree" in fallback_target:
            act_desp = "gathering apples from the apple tree"
          reasoning = f"{reasoning} [retargeted to valid food source]"

  normalized_skill_id = normalize_skill_id(action, target=target, detail=act_desp)

  sim_time = str(getattr(persona.scratch, "curr_time", "unknown"))
  try:
    sim_time = (persona.scratch.curr_time.strftime('%Y-%m-%d %H:%M:%S')
                if (persona.scratch.curr_time and not isinstance(persona.scratch.curr_time, str))
                else str(persona.scratch.curr_time))
    append_debug_log(
      "translation_verify.jsonl",
      {
        "sim_time": sim_time,
        "persona": persona.name,
        "event": "decision_snapshot",
        "intent": thinking_text,
        "llm_decision_text": {
          "thought": thinking_text,
          "reasoning": reasoning,
        },
        "decision": decision,
        "decision_routed_action": action,
        "decision_routed_target": target,
        "decision_routed_detail": act_desp,
        "decision_routed_reasoning": reasoning,
        "collective_social_reroute": bool(collective_social_reroute),
        "explicit_persona_chat_reroute": bool(explicit_persona_chat_reroute),
        "motives": motive_debug,
        "stats": {
          "satiety": persona.scratch.satiety,
          "stamina": persona.scratch.stamina,
          "health": persona.scratch.health,
          "mood": persona.scratch.mood,
        },
        "inventory": persona.scratch.inventory,
      }
    )
    _append_step_decision_trace(
      persona,
      decision_id,
      thinking_text,
      reasoning,
      decision,
      action,
      target,
      act_desp,
      motive_debug,
      minimal_filter_summary,
      collective_social_reroute=collective_social_reroute,
      explicit_persona_chat_reroute=explicit_persona_chat_reroute,
    )
  except Exception:
    pass

  if decision_cache_signature and str(normalized_skill_id or "").lower() in {"gather", "rest", "consume"}:
    put_cached_decision(
      decision_cache_signature,
      {
        "thought": thinking_text,
        "action": action,
        "target": target,
        "detail": act_desp,
        "duration": int(act_dura),
        "reasoning": reasoning,
      }
    )
    try:
      append_debug_log(
        "translation_verify.jsonl",
        {
          "sim_time": sim_time,
          "persona": persona.name,
          "event": "decision_cache_store",
          "intent_family": intent_family,
          "cache_signature": decision_cache_signature,
          "action": action,
          "target": target,
        }
      )
    except Exception:
      pass

  # Fallback check
  if not act_desp:
    act_desp = "idling to conserve energy"
    act_dura = 10

  def tighten_food_action_description(skill_id, raw_target, resolved_address, current_description):
    if str(skill_id or "").lower() != "gather":
      return current_description
    normalized_target = normalize_food_source_target(raw_target)
    address_text = str(resolved_address or "").lower()
    if normalized_target == "refrigerator" or address_text.endswith(":refrigerator"):
      return "opening the refrigerator to gather food items"
    if normalized_target == "stove" or address_text.endswith(":stove"):
      return "preparing food from the stove"
    if normalized_target == "cafe counter" or address_text.endswith(":behind the cafe counter"):
      return "getting prepared food from the cafe counter"
    if normalized_target == "apple tree" or address_text.endswith(":apple tree"):
      return "gathering apples from the apple tree"
    return current_description

  # Resolve sector, arena, object
  phase_started_at = time.perf_counter()
  act_world = maze.access_tile(persona.scratch.curr_tile)["world"]
  resolution_meta = None
  target_persona_name = None
  if normalized_skill_id in {"chat with", "seek_and_chat", "give", "rob"} and target not in {"none", "", None}:
    persona_resolution = resolve_persona_target(personas or {}, target)
    if persona_resolution.get("ok"):
      candidate_target = persona_resolution.get("resolved_target")
      target_persona_name = candidate_target
      new_address = persona_resolution.get("resolved_address")
      resolution_meta = {
        "kind": persona_resolution.get("resolution_kind"),
        "matched": candidate_target,
        "target_type": persona_resolution.get("target_type"),
      }
    else:
      candidate_target = str(target).strip()
      target_persona_name = None
      new_address = persona.scratch.curr_tile and f"<waiting> {persona.scratch.curr_tile[0]} {persona.scratch.curr_tile[1]}" or ""
      resolution_meta = {
        "kind": "persona_target_missing",
        "matched": candidate_target,
        "target_type": "persona",
        "target_resolution_failure": persona_resolution.get("failure_reason"),
      }
      if normalized_skill_id == "chat with" and _is_collective_social_target(target, act_desp):
        location_resolution = resolve_action_target(
          persona,
          maze,
          "hangout_social_venue",
          target=target,
          detail=act_desp,
        )
        if location_resolution.get("ok"):
          normalized_skill_id = "hangout_social_venue"
          action = "hangout_social_venue"
          new_address = location_resolution.get("resolved_address")
          resolution_meta = {
            "kind": "collective_social_target_fallback",
            "matched": location_resolution.get("resolved_target"),
            "target_type": location_resolution.get("target_type"),
            "original_target": candidate_target,
          }
          act_desp = f"relaxing and people-watching at {location_resolution.get('resolved_target')}"
  elif normalized_skill_id == "consume" and _has_inventory_item(persona, target):
    new_address = _current_tile_wait_address(persona)
    resolution_meta = {
      "kind": "inventory_consume_in_place",
      "matched": normalize_food_source_target(target),
      "target_type": "inventory_item",
    }
  else:
    resolution_result = resolve_action_target(
      persona,
      maze,
      normalized_skill_id,
      target=target,
      detail=act_desp,
    )
    if resolution_result.get("ok"):
      new_address = resolution_result.get("resolved_address")
      resolution_meta = {
        "kind": resolution_result.get("resolution_kind"),
        "matched": resolution_result.get("resolved_target"),
        "target_type": resolution_result.get("target_type"),
      }
    else:
      # Fall back to prompt-based location resolution only when deterministic matching fails.
      act_sector = generate_action_sector(act_desp, persona, maze)
      act_arena = generate_action_arena(act_desp, persona, maze, act_world, act_sector)
      act_address = f"{act_world}:{act_sector}:{act_arena}"
      if normalized_skill_id in {"use", "work", "study", "leisure_use", "hangout_social_venue"}:
        new_address = act_address
        resolution_meta = {"kind": "arena_fallback", "matched": act_address}
      else:
        act_game_object = generate_action_game_object(act_desp, act_address, persona, maze)
        new_address = f"{act_world}:{act_sector}:{act_arena}:{act_game_object}"
        resolution_meta = {
          "kind": "llm_object_fallback",
          "matched": act_game_object,
          "target_resolution_failure": resolution_result.get("failure_reason"),
        }
  if normalized_skill_id == "gather" and is_valid_gather_food_source(target):
    available_address = _resolve_food_source_address(persona, target)
    if available_address and available_address != new_address:
      resolution_meta = dict(resolution_meta or {})
      resolution_meta["retargeted_to_available_source"] = available_address
      new_address = available_address
  timings_ms["target_resolution"] = _elapsed_ms(phase_started_at)

  act_desp = tighten_food_action_description(normalized_skill_id, target, new_address, act_desp)

  if normalized_skill_id in {"chat with", "seek_and_chat", "give", "rob"} and target_persona_name:
    act_pron = "💬"
    act_event = (persona.name, normalized_skill_id, target_persona_name)
  else:
    act_pron = generate_action_pronunciatio(act_desp, persona)
    act_event = generate_action_event_triple(act_desp, persona)
  try:
    sim_time = (persona.scratch.curr_time.strftime('%Y-%m-%d %H:%M:%S')
                if (persona.scratch.curr_time and not isinstance(persona.scratch.curr_time, str))
                else str(persona.scratch.curr_time))
    append_debug_log(
      "translation_verify.jsonl",
      {
        "sim_time": sim_time,
        "persona": persona.name,
        "event": "target_resolution",
        "target": target,
        "new_address": new_address,
        "act_description": act_desp,
        "act_event": act_event,
        "act_command_skill": normalized_skill_id,
        "resolution_meta": resolution_meta,
      }
    )
  except Exception:
    pass
  
  # Persona's actions also influence the object states. We set those up here. 
  phase_started_at = time.perf_counter()
  if normalized_skill_id in {"chat with", "seek_and_chat", "give", "rob"} and target not in {"none", "", None}:
    act_obj_desp = None
    act_obj_pron = None
    act_obj_event = (None, None, None)
  else:
    try:
      act_game_object = new_address.split(":")[-1]
    except:
      act_game_object = "none"
    act_obj_desp = generate_act_obj_desc(act_game_object, act_desp, persona)
    act_obj_pron = generate_action_pronunciatio(act_obj_desp, persona)
    act_obj_event = generate_act_obj_event_triple(act_game_object, act_obj_desp, persona)
  timings_ms["object_state"] = _elapsed_ms(phase_started_at)

  # Adding the action to persona's queue. 
  phase_started_at = time.perf_counter()
  action_added = persona.scratch.add_new_action(new_address, 
                                                int(act_dura), 
                                                act_desp, 
                                                act_pron, 
                                                act_event,
                                                build_action_command(action, target, source="decision_translation", raw_action=action, detail=act_desp),
                                                None,
                                                None,
                                                None,
                                                None,
                                                act_obj_desp, 
                                                act_obj_pron, 
                                                act_obj_event,
                                                action_record=_build_action_record(
                                                  persona,
                                                  normalized_skill_id,
                                                  target,
                                                  act_desp,
                                                act_dura,
                                                new_address,
                                                reasoning,
                                                resolution_meta=resolution_meta,
                                                creator_instruction=admin_override_instruction,
                                              ))
  if action_added and admin_override_instruction and getattr(persona.scratch, "clear_admin_override_intent", None):
    persona.scratch.clear_admin_override_intent()
  timings_ms["add_new_action"] = _elapsed_ms(phase_started_at)
  total_ms = _elapsed_ms(decision_started_at)
  _log_timing_event(
    "decide_demand_action_timing",
    {
      "persona": persona.name,
      "curr_step": getattr(persona.scratch, "curr_step", None),
      "act_command_skill": normalized_skill_id,
      "intent_family": intent_family,
      "target": target,
      "new_address": new_address,
      "total_ms": total_ms,
      "timings_ms": timings_ms,
      "minimal_filter_enabled": bool(minimal_filter_summary.get("enabled")),
      "minimal_filter_applied": bool(minimal_filter_summary.get("applied")),
      "minimal_filter_summary": minimal_filter_summary,
    },
  )
  return persona.scratch.act_address


def plan(persona, maze, personas, new_day, retrieved): 
  """
  Main cognitive function of the chain. It takes the retrieved memory and 
  perception, as well as the maze and the first day state to conduct both 
  the long term and short term planning for the persona. 
  """ 
  # If it is a new day, revise identity, but do NOT generate a rigid hourly schedule
  if new_day == "New day":
    revise_identity(persona)

  if getattr(persona.scratch, "should_lock_high_level_planning", lambda: False)():
    _decrement_chatting_with_buffer(persona)
    return persona.scratch.act_address

  # Unify scheduling and survival intercepts into one real-time demand-driven decision engine
  act_desc = persona.scratch.act_description if persona.scratch.act_description else ""
  if persona.scratch.act_check_finished() or not act_desc:
    if act_desc:
      persona.scratch.last_action_desc = act_desc
    if not _get_admin_override_instruction(persona) and persona.scratch.should_resume_suspended_action():
      persona.scratch.resume_suspended_action()
      return persona.scratch.act_address
    decide_demand_action(persona, maze, personas)

  # PART 3: If you perceived an event that needs to be responded to (saw 
  # another persona), and retrieved relevant information. 
  # Step 1: Retrieved may have multiple events represented in it. The first 
  #         job here is to determine which of the events we want to focus 
  #         on for the persona. 
  #         <focused_event> takes the form of a dictionary like this: 
  #         dictionary {["curr_event"] = <ConceptNode>, 
  #                     ["events"] = [<ConceptNode>, ...], 
  #                     ["thoughts"] = [<ConceptNode>, ...]}
  focused_event = False
  if retrieved.keys(): 
    focused_event = _choose_retrieved(persona, retrieved)
  
  # Step 2: Perceived social opportunities are logged as context only.
  # Directly injecting a reaction here would bypass the main decision path.

  # Step 3: Chat-related state clean up. 
  # If the persona is not chatting with anyone, we clean up any of the 
  # chat-related states here. 
  act_event = persona.scratch.act_event
  act_verb = act_event[1] if isinstance(act_event, (list, tuple)) and len(act_event) > 1 else None
  if act_verb not in ["chat with", "creator_comm"]:
    persona.scratch.chatting_with = None
    persona.scratch.chat = None
    persona.scratch.chatting_end_time = None
    clear_social_dialogue_state(persona)
  _decrement_chatting_with_buffer(persona)

  return persona.scratch.act_address


def plan_social_reaction(persona, maze, personas, retrieved):
  """
  Fast-path movement steps no longer inject social reactions outside the
  main decision pipeline.
  """
  _decrement_chatting_with_buffer(persona)
  return persona.scratch.act_address













































 
