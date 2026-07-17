"""Helpers for persisting stat-changing experience memories."""

from persona.cognitive_modules.action_outcomes import build_memory_projection
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


def record_execution_result_experience(persona, description, keywords,
                                       poignancy=5.0,
                                       predicate="experienced",
                                       obj="execution_result",
                                       attribute_effects=None):
  """Persist a non-stat execution result so future decisions can retrieve it as experience."""
  if not getattr(persona, "a_mem", None):
    return None

  normalized_keywords = set(keywords or set())
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


def record_projected_action_outcome(persona, outcome):
  """Persist an outcome's memory projection when its score warrants promotion."""
  if not getattr(persona, "a_mem", None):
    return None
  if not isinstance(outcome, dict) or not outcome:
    return None
  scoring = outcome.get("experience_scoring") or {}
  if not scoring.get("should_promote_to_experience"):
    return None

  projection = dict(outcome.get("memory_projection") or {})
  if not projection:
    projection = build_memory_projection(persona, outcome)
  description = str(projection.get("description") or "").strip()
  if not description:
    return None

  embedding_text = str(projection.get("embedding_text") or description)
  embedding = get_embedding(embedding_text)
  embedding_pair = (embedding_text, embedding)
  keywords = set(projection.get("keywords") or [])
  attribute_effects = projection.get("attribute_effects")
  motive_effects = projection.get("motive_effects")
  memory_tags = projection.get("memory_tags")
  args = (
    persona.scratch.curr_time, None,
    projection.get("subject") or persona.name,
    projection.get("predicate") or "experienced",
    projection.get("object") or "execution_result",
    description, keywords, float(projection.get("poignancy", 5.0) or 5.0),
    embedding_pair, None,
  )
  try:
    return persona.a_mem.add_event(
      *args, attribute_effects=attribute_effects, motive_effects=motive_effects, memory_tags=memory_tags,
    )
  except TypeError as error:
    if "memory_tags" not in str(error) and "motive_effects" not in str(error):
      raise
    return persona.a_mem.add_event(*args, attribute_effects=attribute_effects)
