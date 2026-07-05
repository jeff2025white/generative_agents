from persona.cognitive_modules.debug_log import append_debug_log
from persona.cognitive_modules.memory_effects import (
    capture_attribute_snapshot,
    compute_attribute_effects,
    record_stat_change_experience,
)
from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.cognitive_modules.skill_packs.transfer_skill_utils import (
    are_personas_close,
    choose_inventory_item,
    clear_current_action,
    log_transfer_failure,
    resolve_target_persona,
)


class GiveSkillPack(BaseSkillPack):
    """Transfer one inventory item from the acting NPC to another NPC."""

    def __init__(self):
        super().__init__()
        self.name = "give"
        self.associated_xp = ""

    def can_execute(self, persona, target, maze) -> bool:
        has_item = any(float(count or 0) > 0 for count in (persona.scratch.inventory or {}).values())
        result = bool(str(target or "").strip()) and has_item
        append_debug_log(
            "skill_execution_debug.jsonl",
            {
                "persona": persona.name,
                "skill": "give",
                "event": "can_execute",
                "result": result,
                "target": target,
                "inventory": dict(persona.scratch.inventory or {}),
            },
        )
        return result

    def get_target_tiles(self, persona, target, maze) -> list:
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        target_persona = resolve_target_persona(personas, target)
        if not target_persona:
            log_transfer_failure(persona, "give", target, "target_not_found")
            clear_current_action(persona)
            return
        if target_persona.name == persona.name:
            log_transfer_failure(persona, "give", target, "self_target")
            clear_current_action(persona)
            return
        if not are_personas_close(persona, target_persona):
            log_transfer_failure(
                persona,
                "give",
                target,
                "target_not_close",
                extra={"target_tile": getattr(target_persona.scratch, "curr_tile", None)},
            )
            clear_current_action(persona)
            return

        detail_hint = getattr(persona.scratch, "act_description", None)
        item_name = choose_inventory_item(persona.scratch.inventory, hint_text=detail_hint)
        if not item_name:
            log_transfer_failure(persona, "give", target, "inventory_empty")
            clear_current_action(persona)
            return

        actor_before_inventory = dict(persona.scratch.inventory or {})
        target_before_inventory = dict(target_persona.scratch.inventory or {})
        actor_before_snapshot = capture_attribute_snapshot(persona)
        target_before_snapshot = capture_attribute_snapshot(target_persona)

        persona.scratch.inventory[item_name] = max(0, int(persona.scratch.inventory.get(item_name, 0)) - 1)
        target_persona.scratch.inventory[item_name] = int(target_persona.scratch.inventory.get(item_name, 0)) + 1
        persona.scratch.mood = min(100.0, float(persona.scratch.mood) + 2.0)
        target_persona.scratch.mood = min(100.0, float(target_persona.scratch.mood) + 8.0)

        if getattr(persona, "a_mem", None):
            persona.a_mem.update_relationship(
                target_persona.name,
                relation_type="friend" if persona.a_mem.get_relationship(target_persona.name) is None else None,
                trust_delta=0.12,
                recent_event=f"received a gift of {item_name}",
            )
        if getattr(target_persona, "a_mem", None):
            target_persona.a_mem.update_relationship(
                persona.name,
                relation_type="friend" if target_persona.a_mem.get_relationship(persona.name) is None else None,
                trust_delta=0.18,
                recent_event=f"was gifted {item_name}",
            )

        actor_after_snapshot = capture_attribute_snapshot(persona)
        target_after_snapshot = capture_attribute_snapshot(target_persona)
        actor_effects = compute_attribute_effects(actor_before_snapshot, actor_after_snapshot)
        target_effects = compute_attribute_effects(target_before_snapshot, target_after_snapshot)

        append_debug_log(
            "skill_execution_debug.jsonl",
            {
                "persona": persona.name,
                "skill": "give",
                "event": "on_arrive_end",
                "target": target_persona.name,
                "item": item_name,
                "inventory_before": actor_before_inventory,
                "inventory_after": dict(persona.scratch.inventory or {}),
                "target_inventory_before": target_before_inventory,
                "target_inventory_after": dict(target_persona.scratch.inventory or {}),
                "actor_attribute_effects": actor_effects,
                "target_attribute_effects": target_effects,
            },
        )

        record_stat_change_experience(
            persona,
            f"{persona.name} gave {item_name} to {target_persona.name}.",
            {"give", "gift", "inventory_transfer", str(item_name).lower(), target_persona.name.lower()},
            actor_effects,
            poignancy=5.0,
            predicate="gave",
            obj=target_persona.name,
        )
        record_stat_change_experience(
            target_persona,
            f"{target_persona.name} received {item_name} from {persona.name}.",
            {"receive", "gift", "inventory_transfer", str(item_name).lower(), persona.name.lower()},
            target_effects,
            poignancy=5.0,
            predicate="received",
            obj=persona.name,
        )

        self.finish_success(persona)
