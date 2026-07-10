"""NPC-specific motive state helpers and pure dominant/secondary motive selection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llm_api_config import get_task_route_request_config
from persona.prompt_template.gpt_structure import (
    ChatGPT_safe_generate_response,
    generate_prompt,
)


CORE_STATE_MOTIVES = ("satiety", "stamina", "health", "mood")
DEFAULT_MOTIVE_ORDER = (
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
_PROMPT_TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "prompt_template" / "v2"
INNATE_TRAITS_FROM_MOTIVES_TEMPLATE = str(
    _PROMPT_TEMPLATE_ROOT / "innate_traits_from_motives_v1.txt"
)
INNATE_ROLE_TRAIT_HINTS = {
    "artist": ["imaginative", "expressive"],
    "student": ["inquisitive", "studious"],
    "research": ["inquisitive", "reflective"],
    "teacher": ["patient", "articulate"],
    "cafe": ["friendly", "hospitable"],
    "bar": ["outgoing", "social"],
    "service": ["attentive", "hospitable"],
}
INNATE_MOTIVE_TRAIT_HINTS = {
    "satiety": ["grounded", "practical"],
    "stamina": ["steady", "deliberate"],
    "health": ["careful", "resilient"],
    "safety": ["cautious", "alert"],
    "mood": ["expressive", "sensitive"],
    "belonging": ["warm", "sociable"],
    "status": ["proud", "image-conscious"],
    "autonomy": ["independent", "strong-willed"],
    "competence": ["diligent", "capable"],
    "meaning": ["reflective", "purpose-driven"],
}

MOTIVE_ALIASES = {
    "hunger": "satiety",
    "restore_satiety": "satiety",
    "fatigue": "stamina",
    "restore_stamina": "stamina",
    "survival": "health",
    "comfort_relief": "mood",
    "emotion": "mood",
    "social": "belonging",
    "recognition": "status",
    "control": "autonomy",
    "capability": "competence",
    "meaning_order": "meaning",
    "routine": "meaning",
    "exploration": "meaning",
    "growth": "meaning",
    "curiosity": "meaning",
    "exploration_growth": "meaning",
}

DEFAULT_MOTIVE_TEXT = {
    "satiety": {
        "stable": "我暂时不缺食物，但可以顺带留意之后的进食安排",
        "warning": "我有些饿了，我想尽快吃点东西",
        "desire": "我很饿，我很想进食",
        "guard": "我快饿坏了，我必须立刻进食",
    },
    "stamina": {
        "stable": "我体力还可以，暂时不需要专门休息",
        "warning": "我有点累了，最好尽快休息一下",
        "desire": "我很累，我想休息一下",
        "guard": "我已经撑不住了，我必须立刻休息",
    },
    "health": {
        "stable": "我现在还能撑住，但最好继续留意身体状态",
        "warning": "我身体有些不舒服，我想尽快恢复状态",
        "desire": "我身体不舒服，我想先恢复状态",
        "guard": "我伤得太重了，我必须立刻保命",
    },
    "safety": {
        "stable": "我目前还算安全，但会继续留意周围风险",
        "warning": "我有些没有安全感，我想尽快确认周围是否安全",
        "desire": "我没有安全感，我想先确保自己安全",
        "guard": "我现在很危险，我必须立刻避险",
    },
    "mood": {
        "stable": "我情绪还算平稳，暂时不需要专门调整",
        "warning": "我情绪有点低落，想尽快放松一下",
        "desire": "我情绪很差，我想提升一下情绪",
        "guard": "我太伤心了，我必须立刻提升情绪",
    },
    "belonging": {
        "stable": "我暂时不缺陪伴，但愿意顺带和人待在一起",
        "warning": "我有点孤单，想尽快和人待在一起",
        "desire": "我有点孤单，我想和人待在一起",
        "guard": "我太孤单了，我必须立刻找到陪伴",
    },
    "status": {
        "stable": "我现在不急着证明自己，表现机会可以慢慢找",
        "warning": "我有些在意面子，想尽快证明一下自己",
        "desire": "我很没面子，我要出风头",
        "guard": "我太没面子了，我必须立刻挽回颜面",
    },
    "autonomy": {
        "stable": "我现在还能自己做主，暂时不需要强烈争取主动权",
        "warning": "我有些不想被摆布，想尽快自己做主",
        "desire": "我不想被摆布，我要自己做主",
        "guard": "我受够了被压着，我必须立刻夺回主动权",
    },
    "competence": {
        "stable": "我暂时不急着证明能力，可以顺着手头事情推进",
        "warning": "我想尽快把事情做好，证明自己是有能力的",
        "desire": "我想证明自己能行，我要把事情做好",
        "guard": "我不能再失败了，我必须立刻证明自己",
    },
    "meaning": {
        "stable": "我现在还有方向感，秩序问题可以慢慢整理",
        "warning": "我有些想重新整理方向，尽快让事情回到秩序里",
        "desire": "我想让事情重新有秩序",
        "guard": "我已经失去方向了，我必须立刻找回秩序",
    },
}

DEFAULT_MOTIVE_TEMPLATE = {
    "satiety": {"initial_value": 60.0, "safe_threshold": 50.0, "critical_threshold": 25.0, "decay_per_step": 0.08, "priority_weight": 1.0},
    "stamina": {"initial_value": 75.0, "safe_threshold": 45.0, "critical_threshold": 20.0, "decay_per_step": 0.04, "priority_weight": 1.0},
    "health": {"initial_value": 85.0, "safe_threshold": 55.0, "critical_threshold": 25.0, "decay_per_step": 0.0, "priority_weight": 1.2},
    "safety": {"initial_value": 65.0, "safe_threshold": 45.0, "critical_threshold": 20.0, "decay_per_step": 0.01, "priority_weight": 1.05},
    "mood": {"initial_value": 60.0, "safe_threshold": 50.0, "critical_threshold": 30.0, "decay_per_step": 0.03, "priority_weight": 1.0},
    "belonging": {"initial_value": 58.0, "safe_threshold": 45.0, "critical_threshold": 25.0, "decay_per_step": 0.02, "priority_weight": 0.95},
    "status": {"initial_value": 55.0, "safe_threshold": 42.0, "critical_threshold": 24.0, "decay_per_step": 0.01, "priority_weight": 0.9},
    "autonomy": {"initial_value": 62.0, "safe_threshold": 45.0, "critical_threshold": 25.0, "decay_per_step": 0.01, "priority_weight": 0.9},
    "competence": {"initial_value": 60.0, "safe_threshold": 46.0, "critical_threshold": 28.0, "decay_per_step": 0.015, "priority_weight": 0.92},
    "meaning": {"initial_value": 58.0, "safe_threshold": 44.0, "critical_threshold": 26.0, "decay_per_step": 0.01, "priority_weight": 0.88},
}

PERSONA_MOTIVE_PROFILES = {
    "maria lopez": {
        "satiety": {"initial_value": 58.0, "safe_threshold": 48.0, "critical_threshold": 25.0, "decay_per_step": 0.085},
        "stamina": {"initial_value": 72.0, "safe_threshold": 44.0, "critical_threshold": 20.0, "decay_per_step": 0.05},
        "health": {"initial_value": 84.0, "safe_threshold": 55.0, "critical_threshold": 25.0, "priority_weight": 1.15},
        "safety": {"initial_value": 60.0, "safe_threshold": 43.0, "critical_threshold": 20.0, "decay_per_step": 0.012, "priority_weight": 0.95},
        "mood": {
            "initial_value": 68.0,
            "safe_threshold": 54.0,
            "critical_threshold": 32.0,
            "decay_per_step": 0.035,
            "priority_weight": 1.02,
            "skill_flat_modifiers": {"leisure_use": 4.0, "daydream": 2.0, "sing": 3.0},
        },
        "belonging": {
            "initial_value": 62.0,
            "safe_threshold": 48.0,
            "critical_threshold": 28.0,
            "decay_per_step": 0.03,
            "priority_weight": 1.0,
            "skill_flat_modifiers": {"chat with": 3.0, "hangout_social_venue": 2.0},
        },
        "status": {"initial_value": 58.0, "safe_threshold": 44.0, "critical_threshold": 26.0, "decay_per_step": 0.018, "priority_weight": 0.96},
        "autonomy": {"initial_value": 70.0, "safe_threshold": 50.0, "critical_threshold": 28.0, "decay_per_step": 0.016, "priority_weight": 1.05},
        "competence": {
            "initial_value": 66.0,
            "safe_threshold": 50.0,
            "critical_threshold": 30.0,
            "decay_per_step": 0.022,
            "priority_weight": 1.08,
            "skill_flat_modifiers": {"study": 4.0, "work": 2.0, "creator_task_completion": 2.0},
        },
        "meaning": {"initial_value": 60.0, "safe_threshold": 46.0, "critical_threshold": 28.0, "decay_per_step": 0.014, "priority_weight": 0.94},
    },
    "isabella rodriguez": {
        "satiety": {"initial_value": 62.0, "safe_threshold": 50.0, "critical_threshold": 25.0, "decay_per_step": 0.07},
        "stamina": {"initial_value": 70.0, "safe_threshold": 46.0, "critical_threshold": 20.0, "decay_per_step": 0.045},
        "health": {"initial_value": 86.0, "safe_threshold": 58.0, "critical_threshold": 26.0, "priority_weight": 1.18},
        "safety": {"initial_value": 68.0, "safe_threshold": 48.0, "critical_threshold": 22.0, "decay_per_step": 0.008, "priority_weight": 1.0},
        "mood": {"initial_value": 72.0, "safe_threshold": 58.0, "critical_threshold": 35.0, "decay_per_step": 0.02, "priority_weight": 1.0},
        "belonging": {
            "initial_value": 74.0,
            "safe_threshold": 60.0,
            "critical_threshold": 36.0,
            "decay_per_step": 0.018,
            "priority_weight": 1.15,
            "skill_flat_modifiers": {"chat with": 5.0, "hangout_social_venue": 4.0, "give": 2.0},
        },
        "status": {"initial_value": 64.0, "safe_threshold": 50.0, "critical_threshold": 30.0, "decay_per_step": 0.012, "priority_weight": 1.0},
        "autonomy": {"initial_value": 58.0, "safe_threshold": 44.0, "critical_threshold": 25.0, "decay_per_step": 0.01, "priority_weight": 0.9},
        "competence": {
            "initial_value": 63.0,
            "safe_threshold": 48.0,
            "critical_threshold": 29.0,
            "decay_per_step": 0.017,
            "priority_weight": 0.98,
            "skill_flat_modifiers": {"work": 3.0},
        },
        "meaning": {"initial_value": 61.0, "safe_threshold": 47.0, "critical_threshold": 28.0, "decay_per_step": 0.012, "priority_weight": 0.93},
    },
    "klaus mueller": {
        "satiety": {"initial_value": 57.0, "safe_threshold": 49.0, "critical_threshold": 25.0, "decay_per_step": 0.07},
        "stamina": {"initial_value": 73.0, "safe_threshold": 45.0, "critical_threshold": 20.0, "decay_per_step": 0.038},
        "health": {"initial_value": 85.0, "safe_threshold": 56.0, "critical_threshold": 25.0, "priority_weight": 1.15},
        "safety": {"initial_value": 67.0, "safe_threshold": 47.0, "critical_threshold": 22.0, "decay_per_step": 0.012, "priority_weight": 1.08},
        "mood": {"initial_value": 48.0, "safe_threshold": 62.0, "critical_threshold": 40.0, "decay_per_step": 0.04, "priority_weight": 1.2},
        "belonging": {
            "initial_value": 64.0,
            "safe_threshold": 49.0,
            "critical_threshold": 28.0,
            "decay_per_step": 0.02,
            "priority_weight": 1.02,
            "skill_flat_modifiers": {"chat with": 2.0},
        },
        "status": {"initial_value": 48.0, "safe_threshold": 40.0, "critical_threshold": 22.0, "decay_per_step": 0.008, "priority_weight": 0.75},
        "autonomy": {"initial_value": 63.0, "safe_threshold": 47.0, "critical_threshold": 26.0, "decay_per_step": 0.012, "priority_weight": 0.94},
        "competence": {
            "initial_value": 68.0,
            "safe_threshold": 52.0,
            "critical_threshold": 31.0,
            "decay_per_step": 0.018,
            "priority_weight": 1.08,
            "skill_flat_modifiers": {"study": 3.0},
        },
        "meaning": {
            "initial_value": 74.0,
            "safe_threshold": 60.0,
            "critical_threshold": 36.0,
            "decay_per_step": 0.02,
            "priority_weight": 1.18,
            "skill_flat_modifiers": {"study": 5.0, "work": 2.0, "chat with": 1.0},
        },
    },
}


@dataclass(frozen=True)
class MotivePressure:
    motive: str
    current_value: float
    initial_value: float
    safe_threshold: float
    critical_threshold: float
    priority_weight: float
    decay_per_step: float
    urgency_band: str
    pressure_score: float
    reason: str


def _clamp_0_100(value: Any, default: float) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except Exception:
        return max(0.0, min(100.0, float(default)))


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _canonical_motive_name(name: str) -> str:
    key = str(name or "").strip().lower()
    return MOTIVE_ALIASES.get(key, key or "unknown")


def _deep_copy_mapping(mapping: dict[str, Any] | None) -> dict[str, Any]:
    copied = {}
    for key, value in (mapping or {}).items():
        if isinstance(value, dict):
            copied[key] = dict(value)
        else:
            copied[key] = value
    return copied


def _resolve_persona_profile(name: str | None) -> dict[str, dict[str, Any]]:
    key = str(name or "").strip().lower()
    return _deep_copy_mapping(PERSONA_MOTIVE_PROFILES.get(key))


def build_default_motive_attributes(
    *,
    core_state_values: dict[str, float] | None = None,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    core_state_values = core_state_values or {}
    overrides = overrides or {}
    motive_attributes = {}
    for motive in DEFAULT_MOTIVE_ORDER:
        template = dict(DEFAULT_MOTIVE_TEMPLATE[motive])
        override = _deep_copy_mapping(overrides.get(motive))
        initial_value = _clamp_0_100(
            override.get(
                "initial_value",
                override.get("baseline_value", core_state_values.get(motive, template["initial_value"])),
            ),
            template["initial_value"],
        )
        current_value = _clamp_0_100(
            override.get("current_value", override.get("value", core_state_values.get(motive, initial_value))),
            initial_value,
        )
        motive_attributes[motive] = {
            "current_value": current_value,
            "initial_value": initial_value,
            "safe_threshold": _clamp_0_100(override.get("safe_threshold", template["safe_threshold"]), template["safe_threshold"]),
            "critical_threshold": _clamp_0_100(override.get("critical_threshold", template["critical_threshold"]), template["critical_threshold"]),
            "decay_per_step": max(0.0, _to_float(override.get("decay_per_step", template["decay_per_step"]), template["decay_per_step"])),
            "priority_weight": max(0.1, _to_float(override.get("priority_weight", template["priority_weight"]), template["priority_weight"])),
            "skill_flat_modifiers": _deep_copy_mapping(override.get("skill_flat_modifiers", override.get("flat_bonus", {}))),
            "skill_scale_modifiers": _deep_copy_mapping(override.get("skill_scale_modifiers", override.get("scale_bonus", {}))),
            "stable_text": override.get("stable_text"),
            "warning_text": override.get("warning_text"),
            "desire_text": override.get("desire_text"),
            "guard_text": override.get("guard_text"),
        }
    return motive_attributes


def build_persona_motive_attributes(
    persona_name: str | None,
    *,
    core_state_values: dict[str, float] | None = None,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    merged_overrides = _resolve_persona_profile(persona_name)
    for motive, override in (overrides or {}).items():
        canonical = _canonical_motive_name(motive)
        profile_entry = _deep_copy_mapping(merged_overrides.get(canonical))
        profile_entry.update(_deep_copy_mapping(override))
        merged_overrides[canonical] = profile_entry
    return build_default_motive_attributes(
        core_state_values=core_state_values,
        overrides=merged_overrides,
    )


def normalize_motive_attributes(
    motive_attributes: dict[str, dict[str, Any]] | None,
    *,
    core_state_values: dict[str, float] | None = None,
) -> dict[str, dict[str, Any]]:
    existing = motive_attributes or {}
    normalized = build_default_motive_attributes(core_state_values=core_state_values)
    for raw_name, raw_entry in existing.items():
        motive = _canonical_motive_name(raw_name)
        if motive not in normalized:
            normalized[motive] = {}
        merged = dict(normalized[motive])
        merged.update(_deep_copy_mapping(raw_entry))
        normalized[motive] = build_default_motive_attributes(
            core_state_values={motive: core_state_values.get(motive) if core_state_values else merged.get("current_value")},
            overrides={motive: merged},
        )[motive]
    return normalized


def sync_core_motive_values(
    motive_attributes: dict[str, dict[str, Any]] | None,
    *,
    satiety: float | None = None,
    stamina: float | None = None,
    health: float | None = None,
    mood: float | None = None,
) -> dict[str, dict[str, Any]]:
    normalized = normalize_motive_attributes(
        motive_attributes,
        core_state_values={
            "satiety": satiety if satiety is not None else None,
            "stamina": stamina if stamina is not None else None,
            "health": health if health is not None else None,
            "mood": mood if mood is not None else None,
        },
    )
    for key, value in {"satiety": satiety, "stamina": stamina, "health": health, "mood": mood}.items():
        if value is not None:
            normalized[key]["current_value"] = _clamp_0_100(value, normalized[key]["current_value"])
    return normalized


def apply_passive_motive_decay(
    motive_attributes: dict[str, dict[str, Any]] | None,
    *,
    skip_motives: set[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, float]]:
    normalized = normalize_motive_attributes(motive_attributes)
    skip_motives = {_canonical_motive_name(name) for name in (skip_motives or set())}
    applied = {}
    for motive, entry in normalized.items():
        if motive in skip_motives:
            continue
        decay = max(0.0, _to_float(entry.get("decay_per_step", 0.0), 0.0))
        if decay <= 0.0:
            continue
        before = float(entry["current_value"])
        after = _clamp_0_100(before - decay, before)
        entry["current_value"] = after
        applied[motive] = round(after - before, 3)
    return normalized, applied


def apply_skill_motive_effects(
    motive_attributes: dict[str, dict[str, Any]] | None,
    *,
    skill_id: str,
    motive_effects: dict[str, float] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, float]]:
    normalized = normalize_motive_attributes(motive_attributes)
    applied = {}
    skill_id = str(skill_id or "").strip().lower()
    for raw_motive, base_delta in (motive_effects or {}).items():
        motive = _canonical_motive_name(raw_motive)
        if motive not in normalized:
            continue
        entry = normalized[motive]
        flat_modifiers = _deep_copy_mapping(entry.get("skill_flat_modifiers"))
        scale_modifiers = _deep_copy_mapping(entry.get("skill_scale_modifiers"))
        flat_bonus = _to_float(flat_modifiers.get(skill_id, flat_modifiers.get("*", 0.0)), 0.0)
        scale_bonus = _to_float(scale_modifiers.get(skill_id, scale_modifiers.get("*", 1.0)), 1.0)
        raw_delta = (_to_float(base_delta, 0.0) + flat_bonus) * scale_bonus
        before = float(entry["current_value"])
        after = _clamp_0_100(before + raw_delta, before)
        entry["current_value"] = after
        applied[motive] = round(after - before, 3)
    return normalized, applied


def _compute_pressure(entry: dict[str, Any]) -> MotivePressure:
    current_value = float(entry["current_value"])
    initial_value = max(1.0, float(entry["initial_value"]))
    safe_threshold = max(1.0, float(entry["safe_threshold"]))
    critical_threshold = max(0.0, float(entry["critical_threshold"]))
    priority_weight = float(entry["priority_weight"])
    decay_per_step = max(0.0, float(entry.get("decay_per_step", 0.0)))

    baseline_gap = max(0.0, (initial_value - current_value) / initial_value)
    safe_gap = max(0.0, (safe_threshold - current_value) / safe_threshold)
    critical_gap = 0.0
    if critical_threshold > 0.0:
        critical_gap = max(0.0, (critical_threshold - current_value) / critical_threshold)

    if current_value <= critical_threshold:
        urgency_band = "critical"
    elif current_value <= safe_threshold:
        urgency_band = "warning"
    else:
        urgency_band = "stable"

    pressure_score = (
        baseline_gap * 0.35
        + safe_gap * 0.95
        + critical_gap * 1.8
        + max(0.0, priority_weight - 1.0) * 0.25
        + decay_per_step * 2.5
    )
    if urgency_band == "critical":
        pressure_score += 1.2
    elif urgency_band == "warning":
        pressure_score += 0.35

    reason_parts = [
        f"value={current_value:.1f}",
        f"safe={safe_threshold:.1f}",
        f"critical={critical_threshold:.1f}",
    ]
    if current_value <= critical_threshold:
        reason_parts.append("below_critical_threshold")
    elif current_value <= safe_threshold:
        reason_parts.append("below_safe_threshold")
    if baseline_gap > 0.0:
        reason_parts.append(f"baseline_gap={baseline_gap:.2f}")
    if decay_per_step > 0.0:
        reason_parts.append(f"decay_per_step={decay_per_step:.2f}")

    return MotivePressure(
        motive=str(entry["motive"]),
        current_value=current_value,
        initial_value=initial_value,
        safe_threshold=safe_threshold,
        critical_threshold=critical_threshold,
        priority_weight=priority_weight,
        decay_per_step=decay_per_step,
        urgency_band=urgency_band,
        pressure_score=round(pressure_score, 4),
        reason=", ".join(reason_parts),
    )


def _render_motive_text(entry: dict[str, Any], urgency_band: str) -> str:
    if urgency_band == "critical" and entry.get("guard_text"):
        return str(entry["guard_text"])
    if urgency_band == "warning" and entry.get("warning_text"):
        return str(entry["warning_text"])
    if urgency_band == "warning" and entry.get("desire_text"):
        return str(entry["desire_text"])
    if urgency_band == "stable" and entry.get("stable_text"):
        return str(entry["stable_text"])
    text_pack = DEFAULT_MOTIVE_TEXT.get(
        entry["motive"],
        {
            "stable": f"{entry['motive']} 目前总体稳定，可以作为轻量偏好参考",
            "warning": f"我开始在意{entry['motive']}，最好尽快处理它",
            "desire": f"我很在意{entry['motive']}，我想优先处理它",
            "guard": f"我不能再忽视{entry['motive']}了，我必须立刻处理它",
        },
    )
    if urgency_band == "critical":
        return text_pack["guard"]
    if urgency_band == "warning":
        return text_pack.get("warning", text_pack["desire"])
    return text_pack.get("stable", text_pack["desire"])


def _classify_dominant_strength(primary: MotivePressure) -> str:
    if primary.urgency_band in {"critical", "warning"}:
        return "strong"
    return "strong" if primary.pressure_score >= 0.30 else "weak"


def _should_keep_secondary(primary: MotivePressure, secondary: MotivePressure | None) -> bool:
    if secondary is None:
        return False
    if secondary.urgency_band == "critical":
        return True
    if secondary.urgency_band == "warning":
        return True
    return secondary.pressure_score >= max(0.35, primary.pressure_score * 0.6)


def select_motives(
    motive_attributes: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    if not motive_attributes:
        return {
            "dominant_motive": None,
            "secondary_motive": None,
            "guard_motive": None,
            "dominant_urgency_band": None,
            "dominant_pressure_score": None,
            "dominant_strength": "weak",
            "has_urgent_motive": False,
            "motive_sentence": "",
            "scores": [],
        }
    normalized_attributes = normalize_motive_attributes(motive_attributes)

    normalized_entries = []
    for motive in DEFAULT_MOTIVE_ORDER:
        if motive in normalized_attributes:
            entry = dict(normalized_attributes[motive])
            entry["motive"] = motive
            normalized_entries.append(entry)

    pressures = [_compute_pressure(entry) for entry in normalized_entries]
    pressure_by_name = {pressure.motive: pressure for pressure in pressures}
    sorted_pressures = sorted(
        pressures,
        key=lambda item: (
            2 if item.urgency_band == "critical" else 1 if item.urgency_band == "warning" else 0,
            item.pressure_score,
            item.priority_weight,
        ),
        reverse=True,
    )

    primary = sorted_pressures[0]
    secondary = sorted_pressures[1] if len(sorted_pressures) > 1 else None
    if not _should_keep_secondary(primary, secondary):
        secondary = None

    critical_candidates = [item for item in sorted_pressures if item.urgency_band == "critical"]
    guard_motive = critical_candidates[0].motive if critical_candidates else None
    has_urgent_motive = any(item.urgency_band in {"critical", "warning"} for item in sorted_pressures)
    dominant_strength = _classify_dominant_strength(primary)

    primary_entry = next(entry for entry in normalized_entries if entry["motive"] == primary.motive)
    primary_text = None
    secondary_text = None
    if dominant_strength == "strong":
        primary_text = _render_motive_text(primary_entry, primary.urgency_band)
    if dominant_strength == "strong" and secondary is not None:
        secondary_entry = next(entry for entry in normalized_entries if entry["motive"] == secondary.motive)
        secondary_text = _render_motive_text(secondary_entry, secondary.urgency_band)

    sentence = ""
    if primary_text:
        sentence = primary_text
        if secondary_text:
            sentence = f"{sentence}；{secondary_text}"
        sentence = f"{sentence}。"

    return {
        "dominant_motive": primary.motive,
        "secondary_motive": secondary.motive if secondary else None,
        "guard_motive": guard_motive,
        "dominant_urgency_band": primary.urgency_band,
        "dominant_pressure_score": primary.pressure_score,
        "dominant_strength": dominant_strength,
        "has_urgent_motive": has_urgent_motive,
        "dominant_motive_text": primary_text,
        "secondary_motive_text": secondary_text,
        "motive_sentence": sentence,
        "scores": [
            {
                "motive": item.motive,
                "pressure_score": item.pressure_score,
                "urgency_band": item.urgency_band,
                "current_value": item.current_value,
                "initial_value": item.initial_value,
                "safe_threshold": item.safe_threshold,
                "critical_threshold": item.critical_threshold,
                "priority_weight": item.priority_weight,
                "decay_per_step": item.decay_per_step,
                "reason": item.reason,
            }
            for item in sorted_pressures
        ],
        "reasoning": {
            "dominant_reason": primary.reason,
            "secondary_reason": pressure_by_name.get(secondary.motive).reason if secondary else None,
        },
    }


def summarize_motive_drivers(
    motive_attributes: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    result = select_motives(motive_attributes)
    scores_by_motive = {
        str(item.get("motive")): dict(item)
        for item in (result.get("scores") or [])
        if item.get("motive")
    }

    return {
        **result,
        "scores_by_motive": scores_by_motive,
    }


def summarize_persona_motives(persona_or_scratch: Any) -> dict[str, Any]:
    scratch = getattr(persona_or_scratch, "scratch", persona_or_scratch)
    if scratch is None:
        return summarize_motive_drivers({})

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
    return summarize_motive_drivers(motive_attributes)


def _compact_innate_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").replace("\r", " ").strip().split())


def _build_innate_role_hint_text(scratch: Any) -> str:
    parts = [
        _compact_innate_text(getattr(scratch, "lifestyle", None)),
        _compact_innate_text(getattr(scratch, "learned", None)),
        _compact_innate_text(getattr(scratch, "currently", None)),
    ]
    joined = " ".join(part for part in parts if part).lower()
    hints = []
    for keyword, values in INNATE_ROLE_TRAIT_HINTS.items():
        if keyword in joined:
            hints.extend(values)
    return ", ".join(dict.fromkeys(hints))


def _fallback_innate_traits_from_motives(scratch: Any) -> str:
    summary = summarize_persona_motives(scratch)
    dominant = summary.get("dominant_motive")
    secondary = summary.get("secondary_motive")
    selected = []
    for motive in (dominant, secondary):
        for trait in INNATE_MOTIVE_TRAIT_HINTS.get(str(motive or ""), []):
            if trait not in selected:
                selected.append(trait)
    for trait in _build_innate_role_hint_text(scratch).split(","):
        trait = _compact_innate_text(trait)
        if trait and trait not in selected:
            selected.append(trait)
    existing = _compact_innate_text(getattr(scratch, "innate", None))
    for trait in [item.strip() for item in existing.split(",")]:
        if trait and trait not in selected:
            selected.append(trait)
    if not selected:
        selected = ["grounded", "adaptable", "steady"]
    return ", ".join(selected[:4])


def _build_innate_motive_snapshot_text(scratch: Any) -> str:
    summary = summarize_persona_motives(scratch)
    scores = summary.get("scores") or []
    lines = []
    for item in scores[:5]:
        lines.append(
            (
                f"- {item.get('motive')}: current={float(item.get('current_value', 0.0)):.1f}, "
                f"safe={float(item.get('safe_threshold', 0.0)):.1f}, "
                f"critical={float(item.get('critical_threshold', 0.0)):.1f}, "
                f"priority_weight={float(item.get('priority_weight', 1.0)):.2f}, "
                f"urgency={item.get('urgency_band')}, reason={item.get('reason')}"
            )
        )
    if not lines:
        lines.append("- No motive profile data available.")
    motive_sentence = _compact_innate_text(summary.get("motive_sentence"))
    if motive_sentence:
        lines.append(f"Composite motive sentence: {motive_sentence}")
    return "\n".join(lines)


def _clean_innate_traits_output(raw_text: Any) -> str:
    text = _compact_innate_text(raw_text).strip(" .")
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1].strip()
    text = text.replace(";", ",")
    parts = []
    for part in text.split(","):
        cleaned = _compact_innate_text(part).strip(" .")
        if cleaned and cleaned.lower() not in {"innate traits", "traits"} and cleaned not in parts:
            parts.append(cleaned)
    return ", ".join(parts[:5])


def generate_innate_traits_from_motives(
    persona_or_scratch: Any,
    *,
    force_llm: bool = True,
    request_config: dict[str, Any] | None = None,
) -> str:
    scratch = getattr(persona_or_scratch, "scratch", persona_or_scratch)
    if scratch is None:
        return "grounded, adaptable, steady"

    fallback_text = _fallback_innate_traits_from_motives(scratch)
    if not force_llm:
        return fallback_text

    summary = summarize_persona_motives(scratch)
    prompt_input = [
        getattr(scratch, "name", None) or getattr(persona_or_scratch, "name", None) or "Unknown",
        _compact_innate_text(getattr(scratch, "lifestyle", None)) or "No lifestyle summary available.",
        _compact_innate_text(getattr(scratch, "learned", None)) or "No learned traits summary available.",
        _build_innate_motive_snapshot_text(scratch),
        f"dominant={summary.get('dominant_motive') or 'unknown'}, secondary={summary.get('secondary_motive') or 'unknown'}, guard={summary.get('guard_motive') or 'none'}",
        _build_innate_role_hint_text(scratch) or "No extra role hints.",
    ]
    prompt = generate_prompt(prompt_input, INNATE_TRAITS_FROM_MOTIVES_TEMPLATE)

    def _validate(output, prompt=None):
        cleaned = _clean_innate_traits_output(output)
        return bool(cleaned) and not any(ch.isdigit() for ch in cleaned)

    def _cleanup(output, prompt=None):
        cleaned = _clean_innate_traits_output(output)
        return cleaned or fallback_text

    return ChatGPT_safe_generate_response(
        prompt,
        example_output="friendly, outgoing, hospitable",
        special_instruction=(
            "Return only a short comma-separated innate-traits phrase. "
            "Do not mention motive names, raw numbers, thresholds, or temporary states."
        ),
        repeat=3,
        fail_safe_response=fallback_text,
        func_validate=_validate,
        func_clean_up=_cleanup,
        prompt_kind="innate_traits_summary",
        metadata={"persona": getattr(scratch, "name", None)},
        request_config=request_config or get_task_route_request_config("planning"),
        skip_cache=True,
    )
