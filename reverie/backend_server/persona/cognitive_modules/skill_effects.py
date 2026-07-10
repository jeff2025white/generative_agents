"""Declarative skill effect helpers for base states and NPC-specific motive settlement."""

from __future__ import annotations

from dataclasses import dataclass, field

from persona.cognitive_modules.motive_selector import apply_skill_motive_effects


BASE_STATE_KEYS = ("satiety", "stamina", "health", "mood")
MOTIVE_KEYS = (
    "satiety",
    "stamina",
    "health",
    "safety",
    "mood",
    "belonging",
    "status",
    "autonomy",
    "competence",
    "meaning",
)


def _normalize_mapping(mapping, allowed_keys) -> dict[str, float]:
    normalized = {}
    mapping = mapping or {}
    for key in allowed_keys:
        if key in mapping:
            normalized[key] = round(float(mapping.get(key, 0.0) or 0.0), 3)
    return normalized


@dataclass(frozen=True)
class SkillEffectSpec:
    base_state_effects: dict[str, float] = field(default_factory=dict)
    motive_effects: dict[str, float] = field(default_factory=dict)
    intent_tags: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "base_state_effects": dict(self.base_state_effects),
            "motive_effects": dict(self.motive_effects),
            "intent_tags": list(self.intent_tags),
        }


def build_skill_effect_spec(*, base_state_effects=None, motive_effects=None, intent_tags=None) -> SkillEffectSpec:
    return SkillEffectSpec(
        base_state_effects=_normalize_mapping(base_state_effects, BASE_STATE_KEYS),
        motive_effects=_normalize_mapping(motive_effects, MOTIVE_KEYS),
        intent_tags=tuple(str(tag).strip().lower() for tag in (intent_tags or ()) if str(tag).strip()),
    )


def normalize_skill_effect_spec(spec=None) -> SkillEffectSpec:
    if isinstance(spec, SkillEffectSpec):
        return spec
    if isinstance(spec, dict):
        return build_skill_effect_spec(
            base_state_effects=spec.get("base_state_effects"),
            motive_effects=spec.get("motive_effects"),
            intent_tags=spec.get("intent_tags"),
        )
    return build_skill_effect_spec()


def apply_base_state_effects(persona, base_state_effects=None) -> dict[str, float]:
    scratch = getattr(persona, "scratch", None)
    applied = {}
    effects = _normalize_mapping(base_state_effects, BASE_STATE_KEYS)
    for key in BASE_STATE_KEYS:
        delta = float(effects.get(key, 0.0) or 0.0)
        if delta == 0.0:
            continue
        current_value = float(getattr(scratch, key, 0.0) or 0.0)
        updated_value = max(0.0, min(100.0, current_value + delta))
        setattr(scratch, key, updated_value)
        applied[key] = round(updated_value - current_value, 3)
    if hasattr(scratch, "sync_motive_attributes_from_states"):
        scratch.sync_motive_attributes_from_states()
    return applied


def apply_declared_motive_effects(persona, *, skill_id: str, motive_effects=None) -> dict[str, float]:
    scratch = getattr(persona, "scratch", None)
    motive_attributes = getattr(scratch, "motive_attributes", None)
    updated, applied = apply_skill_motive_effects(
        motive_attributes,
        skill_id=skill_id,
        motive_effects=motive_effects,
    )
    if hasattr(scratch, "set_motive_attributes"):
        scratch.set_motive_attributes(
            updated,
            source="skill_effect",
            reason=skill_id,
            metadata={"applied": applied, "motive_effects": motive_effects or {}},
        )
    else:
        scratch.motive_attributes = updated
    return applied
