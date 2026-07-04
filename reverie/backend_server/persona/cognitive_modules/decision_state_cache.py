import copy
import hashlib
import json


_DECISION_STATE_CACHE = {}


def _bucket(value):
  try:
    value = float(value or 0.0)
  except Exception:
    value = 0.0
  lower = int(value // 10) * 10
  upper = lower + 10
  return f"{lower}_{upper}"


def build_state_signature(persona_name,
                          intent_family,
                          satiety,
                          stamina,
                          health,
                          mood,
                          inventory_state,
                          reachable_targets,
                          cooperative_state):
  normalized = {
    "persona_name": str(persona_name or ""),
    "intent_family": str(intent_family or "generic"),
    "satiety_bucket": _bucket(satiety),
    "stamina_bucket": _bucket(stamina),
    "health_bucket": _bucket(health),
    "mood_bucket": _bucket(mood),
    "inventory_state": str(inventory_state or "empty"),
    "reachable_targets": sorted({str(item or "").strip().lower() for item in (reachable_targets or []) if str(item or "").strip()}),
    "cooperative_state": str(cooperative_state or "none"),
  }
  raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
  return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached_decision(signature):
  decision = _DECISION_STATE_CACHE.get(str(signature or ""))
  if not decision:
    return None
  return copy.deepcopy(decision)


def put_cached_decision(signature, decision):
  if not signature or not isinstance(decision, dict):
    return
  _DECISION_STATE_CACHE[str(signature)] = copy.deepcopy(decision)


def clear_cached_decisions():
  _DECISION_STATE_CACHE.clear()
