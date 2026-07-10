"""Utilities for minimal immediate-step decision constraints."""

from persona.cognitive_modules.food_sources import normalize_food_source_target


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


def build_retry_feedback(reason):
  """Construct one-shot retry guidance after an invalid target is produced."""
  reason = str(reason or "").strip()
  if not reason:
    reason = "The previous target is invalid for this step."
  return (
    reason
    + " Choose another feasible immediate target or a materially different immediate plan. "
    + "If the same underlying need still matters, keep the need but switch to a different reachable target of that type. "
    + "If no suitable target is available, fall back to a clearly feasible alternative such as waiting, idle, or wandering instead of repeating the failed target."
  )
