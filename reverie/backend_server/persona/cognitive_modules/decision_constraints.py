"""Utilities for minimal immediate-step decision constraints."""


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
    return _normalize_invalid_targets(getter(max_age_steps=max_age_steps))

  failure_getter = getattr(scratch, "get_recent_navigation_failure", None)
  if callable(failure_getter):
    failure = failure_getter(max_age_steps=max_age_steps)
  else:
    failure = getattr(scratch, "navigation_failure", None)
  if not failure:
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
    if text.lower() in invalid:
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
  return reason + " Choose another feasible immediate target or a materially different immediate plan."
