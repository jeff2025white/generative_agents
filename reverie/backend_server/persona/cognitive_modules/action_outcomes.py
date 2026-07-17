"""Helpers for building structured action outcome records."""

import hashlib
from datetime import datetime


CORE_ATTRIBUTE_KEYS = ("satiety", "stamina", "health", "mood")


def classify_reason(reason):
    normalized = str(reason or "").strip().lower()
    mapping = {
        "resource_empty": "resource_state",
        "consume_no_food_available": "precondition",
        "path_not_found": "navigation",
        "target_not_found": "resolution",
        "invalid_food_source": "resolution",
        "target_not_close": "resource_state",
        "target_inventory_empty": "resource_state",
    }
    return mapping.get(normalized, "other")


def _normalize_resource_instance_key(target_address):
    text = str(target_address or "").strip()
    return text.lower() if text else None


def _safe_float(value, default=0.0):
    try:
        return float(value or 0.0)
    except Exception:
        return float(default)


def _build_outcome_id(persona_name, curr_step, skill_id, target_address, result, reason):
    base = "|".join(
        [
            str(persona_name or ""),
            str(curr_step or ""),
            str(skill_id or ""),
            str(target_address or ""),
            str(result or ""),
            str(reason or ""),
        ]
    )
    digest = hashlib.md5(base.encode("utf-8")).hexdigest()[:10]
    slug = str(persona_name or "persona").replace(" ", "_")
    return f"{slug}-{curr_step}-{digest}"


def _format_sim_time(curr_time):
    if curr_time is None:
        return None
    if hasattr(curr_time, "strftime"):
        return curr_time.strftime("%Y-%m-%d %H:%M:%S")
    return str(curr_time)


def _default_effects():
    return {
        "self_attribute_effects": {key: 0.0 for key in CORE_ATTRIBUTE_KEYS},
        "inventory_delta": {},
        "progress_score": 0.0,
    }


def _normalize_effects(effects):
    normalized = _default_effects()
    if not isinstance(effects, dict):
        return normalized

    raw_self_effects = effects.get("self_attribute_effects")
    if isinstance(raw_self_effects, dict):
        normalized["self_attribute_effects"] = {
            key: float(raw_self_effects.get(key, 0.0) or 0.0)
            for key in CORE_ATTRIBUTE_KEYS
        }

    inventory_delta = effects.get("inventory_delta")
    if isinstance(inventory_delta, dict):
        normalized["inventory_delta"] = dict(inventory_delta)

    normalized["progress_score"] = _safe_float(effects.get("progress_score", 0.0), default=0.0)

    return normalized


def build_experience_priority_unit(outcome):
    if not isinstance(outcome, dict) or not outcome:
        return None

    action = outcome.get("action") or {}
    execution = outcome.get("execution") or {}
    effects = outcome.get("effects") or {}
    reason = str(execution.get("reason") or "").strip().lower()
    result = str(execution.get("result") or "").strip().lower()
    progress_score = _safe_float(effects.get("progress_score", 0.0), default=0.0)
    resource_type = action.get("target")
    target_address = action.get("target_address")
    instance_key = _normalize_resource_instance_key(target_address)

    if reason in {"resource_empty", "target_not_close", "target_inventory_empty"} and instance_key:
        if reason == "resource_empty":
            evidence_summary = f"{resource_type} at {target_address} was empty recently."
        elif reason == "target_not_close":
            evidence_summary = f"{resource_type} at {target_address} was not close enough to use recently."
        else:
            evidence_summary = f"{resource_type} at {target_address} had no usable inventory recently."
        return {
            "experience_kind": "avoid",
            "intent_family": action.get("intent_family"),
            "skill_id": action.get("skill_id"),
            "resource_scope": "instance",
            "resource_instance_key": instance_key,
            "resource_type": resource_type,
            "recommendation": "avoid_this_instance",
            "confidence": 0.72,
            "freshness_step": outcome.get("curr_step"),
            "evidence_summary": evidence_summary,
            "supporting_outcome_ids": [outcome.get("outcome_id")],
        }

    if result == "success" and instance_key and progress_score >= 0.6:
        return {
            "experience_kind": "prefer",
            "intent_family": action.get("intent_family"),
            "skill_id": action.get("skill_id"),
            "resource_scope": "instance",
            "resource_instance_key": instance_key,
            "resource_type": resource_type,
            "recommendation": "prefer_this_instance",
            "confidence": min(1.0, 0.45 + progress_score * 0.5),
            "freshness_step": outcome.get("curr_step"),
            "evidence_summary": f"{resource_type} at {target_address} worked well recently.",
            "supporting_outcome_ids": [outcome.get("outcome_id")],
        }

    return None


def derive_progress_score_breakdown(skill_id=None, self_attribute_effects=None, inventory_delta=None):
    self_attribute_effects = self_attribute_effects or {}
    inventory_delta = inventory_delta or {}

    def _positive(key):
        try:
            return max(0.0, float(self_attribute_effects.get(key, 0.0) or 0.0))
        except Exception:
            return 0.0

    satiety_gain = _positive("satiety")
    stamina_gain = _positive("stamina")
    health_gain = _positive("health")
    mood_gain = _positive("mood")

    positive_inventory_gain = 0.0
    consumed_inventory_units = 0.0
    for delta in inventory_delta.values():
        try:
            numeric_delta = float(delta or 0.0)
        except Exception:
            numeric_delta = 0.0
        positive_inventory_gain += max(0.0, numeric_delta)
        consumed_inventory_units += abs(min(0.0, numeric_delta))

    attribute_score = min(
        0.7,
        (satiety_gain / 12.0)
        + (stamina_gain / 16.0)
        + (health_gain / 16.0)
        + (mood_gain / 12.0),
    )
    inventory_gain_score = min(0.5, positive_inventory_gain * 0.25)
    conversion_score = 0.15 if consumed_inventory_units > 0 and attribute_score > 0.0 else 0.0
    skill_context_bonus = 0.0
    normalized_skill = str(skill_id or "").strip().lower()
    if normalized_skill in {"gather", "consume", "cook"} and (
        positive_inventory_gain > 0.0 or attribute_score > 0.0
    ):
        skill_context_bonus = 0.1

    total = round(
        min(1.0, attribute_score + inventory_gain_score + conversion_score + skill_context_bonus),
        3,
    )
    return {
        "score": total,
        "attribute_score": round(attribute_score, 3),
        "inventory_gain_score": round(inventory_gain_score, 3),
        "conversion_score": round(conversion_score, 3),
        "skill_context_bonus": round(skill_context_bonus, 3),
        "satiety_gain": round(satiety_gain, 3),
        "stamina_gain": round(stamina_gain, 3),
        "health_gain": round(health_gain, 3),
        "mood_gain": round(mood_gain, 3),
        "positive_inventory_gain": round(positive_inventory_gain, 3),
        "consumed_inventory_units": round(consumed_inventory_units, 3),
    }


def derive_progress_score(skill_id=None, self_attribute_effects=None, inventory_delta=None):
    return derive_progress_score_breakdown(
        skill_id=skill_id,
        self_attribute_effects=self_attribute_effects,
        inventory_delta=inventory_delta,
    )["score"]


def score_action_outcome(effects, reason=None, dominant_motive=None, result=None):
    normalized_effects = _normalize_effects(effects)
    self_effect_magnitude = min(
        1.0,
        sum(abs(float(v or 0.0)) for v in normalized_effects["self_attribute_effects"].values()) / 20.0,
    )
    failure_learning_value = 0.0
    normalized_reason = str(reason or "").strip().lower()
    if normalized_reason in {
        "resource_empty", "consume_no_food_available", "path_not_found", "consume_no_food",
        "target_inventory_empty", "target_not_close", "target_not_found",
        "recent_duplicate_action", "self_chat_target", "invalid_food_source",
        "rest_target_missing",
    }:
        failure_learning_value = 0.72
    elif str(result or "").strip().lower() == "failed":
        failure_learning_value = 0.35

    novelty_value = 0.1 if normalized_effects["inventory_delta"] else 0.0
    dominant_motive_alignment = 0.95 if str(dominant_motive or "").strip().lower() in {
        "satiety",
        "stamina",
        "health",
        "mood",
    } else 0.3

    base_significance = min(
        1.0,
        self_effect_magnitude
        + failure_learning_value
        + novelty_value
        + (dominant_motive_alignment * 0.2)
        + max(0.0, float(normalized_effects["progress_score"])) * 0.3,
    )
    effective_score = round(base_significance, 3)
    return {
        "self_effect_magnitude": round(self_effect_magnitude, 3),
        "other_effect_magnitude": 0.0,
        "failure_learning_value": round(failure_learning_value, 3),
        "novelty_value": round(novelty_value, 3),
        "dominant_motive_alignment": round(dominant_motive_alignment, 3),
        "base_significance": effective_score,
        "recency_weight": 1.0,
        "effective_score": effective_score,
        "should_promote_to_experience": effective_score >= 0.55,
    }


def build_memory_projection(persona, outcome):
    action = outcome.get("action") or {}
    execution = outcome.get("execution") or {}
    decision_context = outcome.get("decision_context") or {}
    effects = outcome.get("effects") or {}
    target = str(action.get("target") or "target").strip()
    target_address = str(action.get("target_address") or "").strip()
    skill_id = str(action.get("skill_id") or "action").strip()
    result = str(execution.get("result") or "unknown").strip().lower()
    reason = str(execution.get("reason") or "").strip().lower()
    persona_name = getattr(persona, "name", None) or outcome.get("persona") or "persona"

    if result == "failed":
        if reason:
            description = (
                f"{persona_name} experienced a failed {skill_id} attempt on {target}"
                + (f" at {target_address}" if target_address else "")
                + f" because {reason}."
            )
        else:
            description = (
                f"{persona_name} experienced a failed {skill_id} attempt on {target}"
                + (f" at {target_address}" if target_address else "")
                + "."
            )
    else:
        description = (
            f"{persona_name} successfully used {skill_id} on {target}"
            + (f" at {target_address}" if target_address else "")
            + "."
        )

    keywords = {
        skill_id.lower(),
        target.lower(),
        result,
        "execution_result",
    }
    if reason:
        keywords.add(reason)
    intent_family = str(action.get("intent_family") or "").strip().lower()
    if intent_family:
        keywords.add(intent_family)
    dominant_motive = str(decision_context.get("dominant_motive") or "").strip().lower()
    if dominant_motive:
        keywords.add(dominant_motive)
    for item_name, delta in (effects.get("inventory_delta") or {}).items():
        item_text = str(item_name or "").strip().lower()
        if item_text:
            keywords.add(item_text)
            if float(delta or 0.0) > 0:
                keywords.add(f"inventory_plus_{item_text}")
            elif float(delta or 0.0) < 0:
                keywords.add(f"inventory_minus_{item_text}")

    return {
        "source_outcome_id": outcome.get("outcome_id"),
        "memory_type": "event",
        "subject": persona_name,
        "predicate": "experienced",
        "object": "execution_result",
        "description": description,
        "embedding_text": description,
        "keywords": sorted(keyword for keyword in keywords if keyword),
        "poignancy": round(4.0 + float((outcome.get("experience_scoring") or {}).get("effective_score", 0.0)) * 4.0, 2),
        "attribute_effects": dict((effects.get("self_attribute_effects") or {})),
        "memory_tags": {
            "skill_id": action.get("skill_id"),
            "target": action.get("target"),
            "target_address": action.get("target_address"),
            "reason": execution.get("reason"),
            "dominant_motive": decision_context.get("dominant_motive"),
            "resource_instance_key": ((outcome.get("resource_context") or {}).get("resource_instance_key")),
        },
    }


def build_action_outcome_record(persona, result, reason=None, payload=None, effects=None):
    scratch = getattr(persona, "scratch", None)
    action_command = getattr(scratch, "act_command", None) or {}
    current_record = getattr(scratch, "current_action_record", None) or {}
    target_address = current_record.get("resolved_address") or getattr(scratch, "act_address", None)
    skill_id = action_command.get("skill_id")
    target = action_command.get("target")
    curr_step = getattr(scratch, "curr_step", None)
    normalized_effects = _normalize_effects(effects)
    decision_context = {
        "decision_id": current_record.get("decision_id"),
        "dominant_motive": current_record.get("dominant_motive"),
    }
    scoring = score_action_outcome(
        normalized_effects,
        reason=reason,
        dominant_motive=decision_context.get("dominant_motive"),
        result=result,
    )

    outcome = {
        "schema_version": 1,
        "outcome_id": _build_outcome_id(
            getattr(persona, "name", None),
            curr_step,
            skill_id,
            target_address,
            result,
            reason,
        ),
        "sim_code": getattr(persona, "sim_code", None),
        "persona": getattr(persona, "name", None),
        "curr_step": curr_step,
        "sim_time": _format_sim_time(getattr(scratch, "curr_time", None)),
        "wall_ts": datetime.now().astimezone().isoformat(),
        "decision_context": decision_context,
        "action": {
            "skill_id": skill_id,
            "raw_action": action_command.get("raw_action"),
            "intent_family": action_command.get("intent_family"),
            "target": target,
            "target_type": current_record.get("target_type"),
            "target_address": target_address,
            "resolved_target": current_record.get("resolved_target") or target,
            "resolution_kind": current_record.get("resolution_kind"),
            "detail": getattr(scratch, "act_description", None),
        },
        "execution": {
            "result": result,
            "reason": reason,
            "reason_class": classify_reason(reason),
            "payload": dict(payload or {}),
        },
        "effects": normalized_effects,
        "resource_context": {
            "resource_type": target,
            "resource_instance_key": _normalize_resource_instance_key(target_address),
        },
        "experience_scoring": scoring,
        "memory_projection": {},
    }
    outcome["memory_projection"] = build_memory_projection(persona, outcome)
    return outcome
