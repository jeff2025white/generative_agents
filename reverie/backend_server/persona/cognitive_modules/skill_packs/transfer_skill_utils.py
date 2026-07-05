"""Shared helpers for NPC-to-NPC inventory transfer skills."""

from persona.cognitive_modules.debug_log import append_debug_log


def resolve_target_persona(personas, target_name):
    """Find a target persona by case-insensitive exact name match."""
    normalized_target = str(target_name or "").strip().lower()
    if not normalized_target:
        return None
    for candidate in personas or []:
        candidate_name = str(getattr(candidate, "name", "") or "").strip().lower()
        if candidate_name == normalized_target:
            return candidate
    return None


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
    """Emit a consistent failure log for transfer-style skills."""
    payload = {
        "persona": persona.name,
        "skill": skill_name,
        "event": "transfer_failed",
        "target": target,
        "reason": reason,
        "inventory": dict(getattr(persona.scratch, "inventory", {}) or {}),
        "curr_tile": getattr(persona.scratch, "curr_tile", None),
        "act_address": getattr(persona.scratch, "act_address", None),
    }
    if extra:
        payload.update(extra)
    append_debug_log("skill_execution_debug.jsonl", payload)
