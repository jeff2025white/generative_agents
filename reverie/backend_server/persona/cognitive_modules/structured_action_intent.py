"""Typed stage-1 action intent validation and deterministic skill compilation."""

from persona.cognitive_modules.action_command_utils import normalize_skill_id


ACTION_CATEGORIES = {
    "avoid",
    "consume",
    "coordinate",
    "gather",
    "give",
    "idle",
    "pressure",
    "recreate",
    "request",
    "rest",
    "rob",
    "socialize",
    "trade",
    "treat",
    "work",
}

TARGET_TYPES = {"persona", "location", "object", "inventory_item", "none"}

INTENT_MODES = {
    "conversation",
    "seek_conversation",
    "social_venue",
    "solo_leisure",
    "wander",
    "daydream",
    "consume",
    "gather",
    "rest",
    "treat",
    "work",
    "study",
    "request",
    "trade",
    "coordinate",
    "pressure",
    "avoid",
    "give",
    "rob",
    "idle",
}

MODE_ALIASES = {
    "chat": "conversation",
    "chat with": "conversation",
    "leisure use": "solo_leisure",
    "request resource": "request",
    "ask for help": "request",
}

SHORT_ACTIONS = {"consume", "request"}

PERSON_ACTIONS = {"request", "trade", "coordinate", "pressure", "avoid", "give", "rob"}
SOCIAL_VENUE_HINTS = {
    "bar",
    "cafe",
    "coffee shop",
    "customer seating",
    "pub",
    "rose and crown",
    "tavern",
}
LOCATION_HINTS = SOCIAL_VENUE_HINTS | {
    "common room",
    "courtyard",
    "garden",
    "park",
    "plaza",
}


def _text(value):
    return str(value or "").strip()


def _normalized(value):
    return " ".join(_text(value).lower().replace("_", " ").split())


def normalize_intent_mode(value):
    """Map harmless spelling variants to the canonical stage-2 mode enum."""
    normalized = _normalized(value)
    canonical_modes = {_normalized(mode): mode for mode in INTENT_MODES}
    return MODE_ALIASES.get(normalized, canonical_modes.get(normalized))


def _contains_hint(text, hints):
    return any(hint in text for hint in hints)


def _persona_names(personas):
    if isinstance(personas, dict):
        candidates = personas.values()
    else:
        candidates = personas or []
    return {
        _normalized(getattr(candidate, "name", ""))
        for candidate in candidates
        if _normalized(getattr(candidate, "name", ""))
    }


def _looks_like_person_name(target):
    tokens = [token for token in _text(target).split() if token]
    return len(tokens) >= 2 and all(token[:1].isupper() for token in tokens[:2])


def normalize_target_type(value):
    normalized = _normalized(value)
    canonical_target_types = {_normalized(target_type): target_type for target_type in TARGET_TYPES}
    aliases = {
        "person": "persona",
        "npc": "persona",
        "place": "location",
        "venue": "location",
        "inventory": "inventory_item",
        "item": "object",
        "resource": "object",
        "": "none",
    }
    return aliases.get(normalized, canonical_target_types.get(normalized, "none"))


def infer_target_type(target, personas=None, inventory=None, detail=None, declared_type=None):
    target_text = _normalized(target)
    detail_text = _normalized(detail)
    combined = f"{target_text} {detail_text}".strip()
    if target_text in {"", "none", "null", "n/a"}:
        return "none"

    known_personas = _persona_names(personas)
    if target_text in known_personas:
        return "persona"
    if personas is None and _looks_like_person_name(target):
        return "persona"

    for item_name, count in (inventory or {}).items():
        try:
            available = float(count or 0) > 0
        except (TypeError, ValueError):
            available = False
        if available and _normalized(item_name) == target_text:
            return "inventory_item"

    if _contains_hint(combined, LOCATION_HINTS):
        return "location"

    declared = normalize_target_type(declared_type)
    if declared in {"location", "inventory_item"}:
        return declared
    if declared == "persona" and not personas:
        return "persona"
    return "object"


def infer_intent_mode(action, target_type, target=None, detail=None, requested_mode=None):
    requested = normalize_intent_mode(requested_mode)
    if requested:
        return requested

    action_key = _normalized(action)
    context = f"{_normalized(target)} {_normalized(detail)}".strip()
    if action_key == "socialize":
        if target_type == "persona":
            return "seek_conversation"
        if _contains_hint(context, SOCIAL_VENUE_HINTS):
            return "social_venue"
        return "wander"
    if action_key == "recreate":
        if _contains_hint(context, SOCIAL_VENUE_HINTS):
            return "social_venue"
        if _contains_hint(context, {"walk", "wander", "stroll", "park", "garden", "plaza"}):
            return "wander"
        if _contains_hint(context, {"daydream", "people-watch", "people watch", "zone out"}):
            return "daydream"
        return "solo_leisure"
    if action_key == "work" and _contains_hint(context, {"book", "homework", "read", "research", "study"}):
        return "study"
    return action_key if action_key in INTENT_MODES else "idle"


def normalize_action_intent_contract(decision):
    """Repair recoverable contract differences without changing action semantics."""
    if not isinstance(decision, dict):
        return decision

    normalized_decision = dict(decision)
    corrections = list(normalized_decision.get("contract_corrections") or [])
    action = _normalized(normalized_decision.get("action"))

    if "target_type" in normalized_decision:
        raw_target_type = _text(normalized_decision.get("target_type"))
        normalized_target_type = _normalized(raw_target_type)
        valid_target_type_inputs = {_normalized(value) for value in TARGET_TYPES} | {
            "person", "npc", "place", "venue", "inventory", "item", "resource", ""
        }
        target_type = (
            normalize_target_type(raw_target_type)
            if normalized_target_type in valid_target_type_inputs
            else normalized_target_type
        )
        if raw_target_type != target_type:
            corrections.append(f"target_type:{raw_target_type or 'empty'}->{target_type}")
        normalized_decision["target_type"] = target_type
    else:
        target_type = "none"

    raw_mode = _text(normalized_decision.get("mode"))
    mode = normalize_intent_mode(raw_mode)
    if not mode and _normalized(raw_mode) in {"", "none", "null", "n/a"}:
        mode = infer_intent_mode(
            action,
            target_type,
            target=normalized_decision.get("target"),
            detail=normalized_decision.get("detail"),
        )
    if mode:
        if raw_mode != mode:
            corrections.append(f"mode:{raw_mode or 'empty'}->{mode}")
        normalized_decision["mode"] = mode

    min_duration = 5 if action in SHORT_ACTIONS else 10
    raw_duration = normalized_decision.get("duration")
    try:
        duration = int(raw_duration)
    except (TypeError, ValueError):
        duration = min_duration
    duration = max(min_duration, min(duration, 120))
    if raw_duration != duration:
        corrections.append(f"duration:{raw_duration}->{duration}")
    normalized_decision["duration"] = duration

    if corrections:
        normalized_decision["contract_corrections"] = corrections
    return normalized_decision


def validate_action_intent_shape(decision, require_typed_fields=True):
    if not isinstance(decision, dict):
        return False, ["decision_not_object"]

    decision = normalize_action_intent_contract(decision)

    required = {"thought", "action", "target", "detail", "duration", "reasoning"}
    if require_typed_fields:
        required.update({"schema_version", "target_type", "mode", "topic"})
    errors = [f"missing_{key}" for key in sorted(required) if key not in decision]

    action = _normalized(decision.get("action"))
    if action not in ACTION_CATEGORIES:
        errors.append("invalid_action")
    if require_typed_fields:
        try:
            if int(decision.get("schema_version")) != 2:
                errors.append("invalid_schema_version")
        except (TypeError, ValueError):
            errors.append("invalid_schema_version")
        raw_target_type = _normalized(decision.get("target_type"))
        valid_target_type_inputs = {_normalized(value) for value in TARGET_TYPES} | {
            "person", "npc", "place", "venue", "inventory", "item", "resource"
        }
        if raw_target_type not in valid_target_type_inputs:
            errors.append("invalid_target_type")
    if require_typed_fields and normalize_intent_mode(decision.get("mode")) not in INTENT_MODES:
        errors.append("invalid_mode")
    try:
        duration = int(decision.get("duration"))
        min_duration = 5 if action in SHORT_ACTIONS else 10
        if duration < min_duration or duration > 120:
            errors.append("invalid_duration")
    except (TypeError, ValueError):
        errors.append("invalid_duration")
    return not errors, errors


def compile_action_intent(decision, personas=None, inventory=None):
    """Compile a model-facing action category into a stable runtime skill id."""
    normalized_decision = normalize_action_intent_contract(decision)
    normalized_decision = normalized_decision if isinstance(normalized_decision, dict) else {}
    action = _normalized(normalized_decision.get("action")) or "idle"
    target = _text(normalized_decision.get("target")) or "none"
    detail = _text(normalized_decision.get("detail")) or "idling"
    declared_target_type = normalize_target_type(normalized_decision.get("target_type"))
    target_type = infer_target_type(
        target,
        personas=personas,
        inventory=inventory,
        detail=detail,
        declared_type=declared_target_type,
    )
    mode = infer_intent_mode(
        action,
        target_type,
        target=target,
        detail=detail,
        requested_mode=normalized_decision.get("mode"),
    )
    corrections = list(normalized_decision.get("contract_corrections") or [])
    if declared_target_type != target_type:
        corrections.append(f"target_type:{declared_target_type}->{target_type}")

    if action == "socialize":
        if target_type == "persona":
            skill_id = "seek_and_chat"
            if mode not in {"conversation", "seek_conversation"}:
                corrections.append(f"mode:{mode}->seek_conversation")
                mode = "seek_conversation"
        elif mode == "social_venue" or _contains_hint(_normalized(f"{target} {detail}"), SOCIAL_VENUE_HINTS):
            skill_id = "hangout_social_venue"
        elif target_type == "location":
            skill_id = "wander"
        else:
            skill_id = "leisure_use"
    elif action == "recreate":
        if mode == "social_venue":
            skill_id = "hangout_social_venue"
        elif mode == "wander":
            skill_id = "wander"
        elif mode == "daydream":
            skill_id = "daydream"
        else:
            skill_id = "leisure_use"
    elif action == "work" and mode == "study":
        skill_id = "study"
    elif action in PERSON_ACTIONS and target_type != "persona":
        skill_id = "idle"
        corrections.append(f"{action}_requires_persona")
    else:
        skill_id = normalize_skill_id(action, target=target, detail=detail) or "idle"

    try:
        schema_version = int(normalized_decision.get("schema_version") or 2)
    except (TypeError, ValueError):
        schema_version = 2
        corrections.append("schema_version:invalid->2")
    normalized_decision.update({
        "schema_version": schema_version,
        "target": target,
        "target_type": target_type,
        "mode": mode,
        "topic": _text(normalized_decision.get("topic")),
        "compiled_skill_id": skill_id,
    })
    if corrections:
        normalized_decision["contract_corrections"] = corrections
    return normalized_decision
