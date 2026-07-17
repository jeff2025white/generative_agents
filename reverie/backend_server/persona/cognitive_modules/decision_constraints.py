"""Read-only validation utilities for observing LLM decision correction."""

import json

from persona.cognitive_modules.food_sources import (
  is_valid_gather_food_source,
  normalize_food_source_target,
)


def _normalize_invalid_targets(targets):
  """Normalize and de-duplicate invalid target names while preserving order."""
  normalized = []
  seen = set()
  for item in targets or []:
    text = str(item or "").strip()
    if not text:
      continue
    lowered = text.lower()
    if lowered in seen:
      continue
    seen.add(lowered)
    normalized.append(text)
  return normalized


def build_invalid_targets(scratch, max_age_steps=6):
  """Build an immediate-step blacklist from the most recent navigation failure."""
  if scratch is None:
    return []

  getter = getattr(scratch, "get_recent_invalid_targets", None)
  if callable(getter):
    invalid_targets = _normalize_invalid_targets(getter(max_age_steps=max_age_steps))
    if invalid_targets:
      return invalid_targets

  current_step = getattr(scratch, "curr_step", None)
  failed_instances = []
  for item in (getattr(scratch, "failed_resource_instances", None) or []):
    if not isinstance(item, dict):
      continue
    expires_after = item.get("expires_after_step")
    if current_step is not None and expires_after is not None and expires_after < current_step:
      continue
    reason = str(item.get("reason") or "").strip().lower()
    if reason == "resource_empty":
      continue
    failed_instances.append(item.get("target"))
  invalid_targets = _normalize_invalid_targets(failed_instances)
  if invalid_targets:
    return invalid_targets

  failure_getter = getattr(scratch, "get_recent_navigation_failure", None)
  if callable(failure_getter):
    failure = failure_getter(max_age_steps=max_age_steps)
  else:
    failure = getattr(scratch, "navigation_failure", None)
  if not failure:
    return []
  if str(failure.get("reason") or "").strip().lower() == "resource_empty":
    return []

  return _normalize_invalid_targets([failure.get("target")])


def filter_invalid_resources(resources, invalid_targets):
  """Remove immediate-step invalid targets from the nearby resource candidates."""
  invalid = {item.lower() for item in _normalize_invalid_targets(invalid_targets)}
  filtered = []
  for item in resources or []:
    text = str(item or "").strip()
    if not text:
      continue
    normalized_text = text
    if "(" in normalized_text:
      normalized_text = normalized_text.split("(", 1)[0].strip()
    canonical_text = normalize_food_source_target(normalized_text)
    if text.lower() in invalid or str(canonical_text or "").strip().lower() in invalid:
      continue
    filtered.append(item)
  return filtered


def validate_decision_target(decision, invalid_targets):
  """Check whether the chosen target hits the immediate-step blacklist."""
  target = str((decision or {}).get("target") or "").strip().lower()
  invalid = {item.lower() for item in _normalize_invalid_targets(invalid_targets)}
  if target and target in invalid:
    return True, f"The target {target} is invalid for this step because it just failed and is currently unreachable."
  return False, ""


def _positive_inventory(inventory):
  result = {}
  for item, count in (inventory or {}).items():
    try:
      numeric_count = int(count or 0)
    except Exception:
      numeric_count = 0
    if numeric_count > 0:
      result[str(item)] = numeric_count
  return result


def _resource_state_for_target(object_states, target):
  target_text = str(target or "").strip().lower()
  canonical_target = str(normalize_food_source_target(target) or target).strip().lower()
  for item in object_states or []:
    text = str(item or "").strip()
    label = text.split("(", 1)[0].strip().lower()
    canonical_label = str(normalize_food_source_target(label) or label).strip().lower()
    if target_text in {label, canonical_label} or canonical_target in {label, canonical_label}:
      return text
  return None


def validate_decision(decision, *, invalid_targets=None, inventory=None,
                      object_states=None, persona_name=None, known_personas=None):
  """Return objective validity evidence without selecting or rewriting an action."""
  decision = decision or {}
  action = str(decision.get("action") or "").strip().lower()
  target = str(decision.get("target") or "").strip()
  target_lower = target.lower()

  target_invalid, target_reason = validate_decision_target(decision, invalid_targets)
  if target_invalid:
    return {
      "valid": False,
      "reason_code": "recent_target_failure",
      "message": target_reason,
      "evidence": {
        "selected_target": target,
        "recently_invalid_targets": _normalize_invalid_targets(invalid_targets),
      },
    }

  if action == "consume":
    available_inventory = _positive_inventory(inventory)
    matching_count = next(
      (count for item, count in available_inventory.items() if item.strip().lower() == target_lower),
      0,
    )
    if matching_count <= 0:
      return {
        "valid": False,
        "reason_code": "inventory_missing",
        "message": f"Consume requires the selected item '{target}' to exist in inventory.",
        "evidence": {
          "selected_target": target,
          "inventory": available_inventory,
          "required_count": 1,
          "observed_count": matching_count,
        },
      }

  if action == "gather":
    canonical_target = normalize_food_source_target(target)
    if not is_valid_gather_food_source(canonical_target):
      return {
        "valid": False,
        "reason_code": "invalid_food_source",
        "message": f"Gather target '{target}' is not a configured food source.",
        "evidence": {"selected_target": target},
      }
    resource_state = _resource_state_for_target(object_states, target)
    if resource_state and "stock: empty" in resource_state.lower():
      return {
        "valid": False,
        "reason_code": "resource_empty",
        "message": f"Gather target '{target}' is currently empty.",
        "evidence": {
          "selected_target": target,
          "observed_resource_state": resource_state,
        },
      }

  if action in {"socialize", "request", "trade", "coordinate", "pressure", "avoid", "give", "rob"}:
    if persona_name and target_lower == str(persona_name).strip().lower():
      return {
        "valid": False,
        "reason_code": "self_target",
        "message": f"Action '{action}' cannot target the acting persona.",
        "evidence": {"selected_target": target, "persona": persona_name},
      }
    if known_personas is not None:
      if isinstance(known_personas, dict):
        persona_by_name = {
          str(name).strip().lower(): persona
          for name, persona in known_personas.items()
        }
      else:
        persona_by_name = {
          str(getattr(persona, "name", persona)).strip().lower(): persona
          for persona in known_personas
        }
      names = [str(getattr(persona, "name", name)) for name, persona in persona_by_name.items()]
      if target_lower not in persona_by_name:
        return {
          "valid": False,
          "reason_code": "persona_not_found",
          "message": f"Persona target '{target}' is not present in the current simulation context.",
          "evidence": {"selected_target": target, "present_personas": names},
        }
      target_persona = persona_by_name.get(target_lower)
      if action in {"request", "trade"} and target_persona is not None:
        target_inventory = _positive_inventory(
          getattr(getattr(target_persona, "scratch", None), "inventory", {}) or {}
        )
        if not target_inventory:
          return {
            "valid": False,
            "reason_code": "target_inventory_empty",
            "message": f"Persona target '{target}' has no transferable inventory.",
            "evidence": {
              "selected_target": target,
              "target_inventory": target_inventory,
            },
          }

  return {
    "valid": True,
    "reason_code": None,
    "message": "Decision passed read-only validation.",
    "evidence": {},
  }


def build_retry_feedback(validation, mode="evaluation"):
  """Return failure evidence without prescribing the replacement decision."""
  if isinstance(validation, dict):
    payload = {
      "validation_result": "rejected",
      "reason_code": validation.get("reason_code"),
      "message": validation.get("message"),
      "evidence": validation.get("evidence") or {},
    }
  else:
    payload = {
      "validation_result": "rejected",
      "reason_code": "invalid_decision",
      "message": str(validation or "The previous decision is invalid."),
      "evidence": {},
    }
  instruction = (
    "Revise the immediate decision using the current world state and the objective evidence. "
    "Return a complete decision. The validator will not choose an action or target for you."
  )
  if str(mode or "evaluation").strip().lower() == "production":
    instruction += " Respect all stated physical preconditions and do not repeat a rejected decision unless its evidence changed."
  return "VALIDATION_FEEDBACK\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n" + instruction
