"""Shared helpers for NPC-to-NPC inventory transfer skills."""

from persona.cognitive_modules.action_target_resolver import resolve_target_persona as _resolve_target_persona


def resolve_target_persona(personas, target_name):
    """Find a target persona by case-insensitive exact name match."""
    candidate, _candidate_name = _resolve_target_persona(personas, target_name)
    return candidate


def choose_inventory_item(inventory, hint_text=None):
    """Pick an inventory item, preferring one mentioned in the free-form hint."""
    inventory = inventory or {}
    positive_items = [
        str(item)
        for item, count in inventory.items()
        if float(count or 0) > 0
    ]
    if not positive_items:
        return None

    hint = str(hint_text or "").strip().lower()
    for item in positive_items:
        if item.lower() in hint:
            return item
    return sorted(positive_items, key=lambda value: value.lower())[0]


def are_personas_close(persona_a, persona_b, max_distance=2):
    """Return True when two personas are close enough for hand-to-hand transfer."""
    tile_a = getattr(getattr(persona_a, "scratch", None), "curr_tile", None)
    tile_b = getattr(getattr(persona_b, "scratch", None), "curr_tile", None)
    if not tile_a or not tile_b:
        return True
    try:
        distance = abs(int(tile_a[0]) - int(tile_b[0])) + abs(int(tile_a[1]) - int(tile_b[1]))
    except Exception:
        return True
    return distance <= max_distance


def clear_current_action(persona):
    """Release the current action so the planner can select the next step."""
    if hasattr(persona.scratch, "clear_current_action"):
        persona.scratch.clear_current_action()
        return
    persona.scratch.planned_path = []
    persona.scratch.act_path_set = False
    persona.scratch.act_address = None
    persona.scratch.act_description = None
    persona.scratch.act_event = None
    persona.scratch.act_command = None

def log_transfer_failure(persona, skill_name, target, reason, extra=None):
    """Legacy skill execution logs are retired; keep the helper as a no-op."""
    return None
