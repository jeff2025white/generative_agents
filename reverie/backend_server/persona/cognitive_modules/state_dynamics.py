"""Shared per-step state dynamics used by simulation and motivation forecasting."""

from __future__ import annotations


STATE_KEYS = ("satiety", "stamina", "health", "mood")


def _clamp_stat(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _safe_lower(value) -> str:
    return str(value or "").strip().lower()


def derive_step_state_deltas(
    persona,
    *,
    curr_time=None,
    act_description=None,
    chatting_with=None,
    planned_path=None,
) -> dict[str, float]:
    """Return the current one-step state deltas without mutating persona state."""
    scratch = getattr(persona, "scratch", None)
    satiety = float(getattr(scratch, "satiety", 0.0) or 0.0)
    stamina = float(getattr(scratch, "stamina", 0.0) or 0.0)
    health = float(getattr(scratch, "health", 0.0) or 0.0)
    mood = float(getattr(scratch, "mood", 0.0) or 0.0)

    if health <= 0.0:
        return {
            "satiety": round(-satiety, 3),
            "stamina": round(-stamina, 3),
            "health": round(-health, 3),
            "mood": round(-mood, 3),
        }

    act_desc = _safe_lower(act_description if act_description is not None else getattr(scratch, "act_description", ""))
    chatting_with = chatting_with if chatting_with is not None else getattr(scratch, "chatting_with", None)
    planned_path = planned_path if planned_path is not None else getattr(scratch, "planned_path", None)
    active_execution_state = getattr(scratch, "active_execution_state", None) or {}
    execution_phase = _safe_lower(active_execution_state.get("phase"))
    is_in_transit = bool(planned_path) or execution_phase == "pathing"

    is_sleeping = (not is_in_transit) and ("sleeping" in act_desc or "sleep" in act_desc)
    is_resting = (not is_in_transit) and ("resting" in act_desc or "rest" in act_desc)
    is_social = bool(chatting_with and chatting_with not in {"", "<creator>"})

    motive_attributes = getattr(scratch, "motive_attributes", {}) or {}
    satiety_entry = motive_attributes.get("satiety") or {}
    stamina_entry = motive_attributes.get("stamina") or {}
    mood_entry = motive_attributes.get("mood") or {}

    satiety_decay = satiety_entry.get("decay_per_step")
    satiety_decay = float(satiety_decay) if satiety_decay is not None else 0.08

    stamina_decay = stamina_entry.get("decay_per_step")
    stamina_decay = float(stamina_decay) if stamina_decay is not None else 0.04

    mood_decay = mood_entry.get("decay_per_step")
    mood_decay = float(mood_decay) if mood_decay is not None else 0.03

    satiety_delta = -satiety_decay / 2.0 if is_sleeping else -satiety_decay
    if is_sleeping:
        stamina_delta = 0.15
    elif is_resting:
        stamina_delta = 0.08
    else:
        stamina_delta = -stamina_decay * 1.75 if planned_path else -stamina_decay

    projected_satiety = _clamp_stat(satiety + satiety_delta)
    projected_stamina = _clamp_stat(stamina + stamina_delta)

    mood_delta = 0.30 if is_social else -mood_decay * 2.0

    if projected_satiety >= 80.0:
        mood_delta += 0.02
    elif projected_satiety < 20.0:
        mood_delta -= 0.08

    if projected_stamina >= 80.0:
        mood_delta += 0.02
    elif projected_stamina < 20.0:
        mood_delta -= 0.06

    projected_mood = _clamp_stat(mood + mood_delta)

    health_delta = 0.0
    if projected_satiety <= 0.0:
        health_delta -= 0.05
    if projected_stamina <= 0.0:
        health_delta -= 0.02
    if projected_mood < 20.0:
        health_delta -= 0.02
    if projected_satiety > 50.0 and projected_stamina > 50.0 and projected_mood > 50.0:
        health_delta += 0.01

    return {
        "satiety": round(satiety_delta, 3),
        "stamina": round(stamina_delta, 3),
        "health": round(health_delta, 3),
        "mood": round(mood_delta, 3),
    }


def apply_step_state_dynamics(persona, *, curr_time=None) -> dict[str, float]:
    """Apply the shared one-step dynamics to a persona in place."""
    scratch = getattr(persona, "scratch", None)
    deltas = derive_step_state_deltas(persona, curr_time=curr_time)
    if float(getattr(scratch, "health", 0.0) or 0.0) <= 0.0:
        scratch.satiety = 0.0
        scratch.stamina = 0.0
        scratch.health = 0.0
        scratch.mood = 0.0
        return deltas

    scratch.satiety = _clamp_stat(float(getattr(scratch, "satiety", 0.0) or 0.0) + deltas["satiety"])
    scratch.stamina = _clamp_stat(float(getattr(scratch, "stamina", 0.0) or 0.0) + deltas["stamina"])
    scratch.mood = _clamp_stat(float(getattr(scratch, "mood", 0.0) or 0.0) + deltas["mood"])
    scratch.health = _clamp_stat(float(getattr(scratch, "health", 0.0) or 0.0) + deltas["health"])

    chatting_with = getattr(scratch, "chatting_with", None)
    if chatting_with and chatting_with not in {"", "<creator>"} and curr_time is not None:
        scratch.last_social_time = curr_time

    return deltas
