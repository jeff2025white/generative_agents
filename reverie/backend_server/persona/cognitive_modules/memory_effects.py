"""Helpers for persisting stat-changing experience memories."""

from persona.prompt_template.gpt_structure import get_embedding


ATTRIBUTE_KEYS = ("satiety", "stamina", "health", "mood")


def capture_attribute_snapshot(persona):
  """Capture the persona's four tracked physical and emotional attributes."""
  snapshot = {}
  for key in ATTRIBUTE_KEYS:
    try:
      snapshot[key] = float(getattr(persona.scratch, key, 0.0) or 0.0)
    except Exception:
      snapshot[key] = 0.0
  return snapshot


def compute_attribute_effects(before_snapshot, after_snapshot):
  """Convert two attribute snapshots into a numeric delta mapping."""
  effects = {}
  before_snapshot = before_snapshot or {}
  after_snapshot = after_snapshot or {}
  for key in ATTRIBUTE_KEYS:
    before_val = float(before_snapshot.get(key, 0.0) or 0.0)
    after_val = float(after_snapshot.get(key, 0.0) or 0.0)
    effects[key] = round(after_val - before_val, 3)
  return effects


def has_meaningful_attribute_effects(attribute_effects, epsilon=0.01):
  """Return True when any tracked attribute changed enough to matter."""
  if not isinstance(attribute_effects, dict):
    return False
  return any(abs(float(attribute_effects.get(key, 0.0) or 0.0)) >= epsilon
             for key in ATTRIBUTE_KEYS)


def build_effect_keywords(attribute_effects):
  """Generate retrieval keywords from the sign of each attribute delta."""
  keywords = set()
  if not isinstance(attribute_effects, dict):
    return keywords
  for key in ATTRIBUTE_KEYS:
    delta = float(attribute_effects.get(key, 0.0) or 0.0)
    if delta > 0:
      keywords.update({key, f"{key}_up", f"increase_{key}", f"restore_{key}"})
    elif delta < 0:
      keywords.update({key, f"{key}_down", f"decrease_{key}", f"cost_{key}"})
  return keywords


def record_stat_change_experience(persona, description, keywords,
                                  attribute_effects, poignancy=6.0,
                                  predicate="experienced",
                                  obj="attribute_change"):
  """Persist a direct experience memory tagged with attribute deltas."""
  if not getattr(persona, "a_mem", None):
    return None
  if not has_meaningful_attribute_effects(attribute_effects):
    return None

  normalized_keywords = set(keywords or set())
  normalized_keywords.update(build_effect_keywords(attribute_effects))
  embedding = get_embedding(description)
  embedding_pair = (description, embedding)
  return persona.a_mem.add_event(
    persona.scratch.curr_time,
    None,
    persona.name,
    predicate,
    obj,
    description,
    normalized_keywords,
    float(poignancy),
    embedding_pair,
    None,
    attribute_effects=attribute_effects,
  )
