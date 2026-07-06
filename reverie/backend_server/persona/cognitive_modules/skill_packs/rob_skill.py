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
    log_transfer_failure,
    resolve_target_persona,
)


class RobSkillPack(BaseSkillPack):
    """Steal one inventory item from another NPC."""

    def __init__(self):
        super().__init__()
        self.name = "rob"
        self.associated_xp = ""

    def can_execute(self, persona, target, maze) -> bool:
        result = bool(str(target or "").strip())
        append_debug_log(
            "skill_execution_debug.jsonl",
            {
                "persona": persona.name,
                "skill": "rob",
                "event": "can_execute",
                "result": result,
                "target": target,
                "inventory": dict(persona.scratch.inventory or {}),
            },
        )
        if not str(target or "").strip():
            return self.set_precheck_result(False, "target_missing", {})
        return self.set_precheck_result(True, "ready_to_rob", {"target": target})

    def get_target_tiles(self, persona, target, maze) -> list:
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        target_persona = resolve_target_persona(personas, target)
        if not target_persona:
            log_transfer_failure(persona, "rob", target, "target_not_found")
            self.finish_failure(persona, "target_not_found", {"target": target})
            return
        if target_persona.name == persona.name:
            log_transfer_failure(persona, "rob", target, "self_target")
            self.finish_failure(persona, "self_target", {"target": target})
            return
        if not are_personas_close(persona, target_persona):
            log_transfer_failure(
                persona,
                "rob",
                target,
                "target_not_close",
                extra={"target_tile": getattr(target_persona.scratch, "curr_tile", None)},
            )
            self.finish_failure(
                persona,
                "target_not_close",
                {"target": target, "target_tile": getattr(target_persona.scratch, "curr_tile", None)},
            )
            return

        detail_hint = getattr(persona.scratch, "act_description", None)
        item_name = choose_inventory_item(target_persona.scratch.inventory, hint_text=detail_hint)
        if not item_name:
            log_transfer_failure(
                persona,
                "rob",
                target,
                "target_inventory_empty",
                extra={"target_inventory": dict(target_persona.scratch.inventory or {})},
            )
            self.finish_failure(
                persona,
                "target_inventory_empty",
                {"target": target, "target_inventory": dict(target_persona.scratch.inventory or {})},
            )
            return

        actor_before_inventory = dict(persona.scratch.inventory or {})
        target_before_inventory = dict(target_persona.scratch.inventory or {})
        actor_before_snapshot = capture_attribute_snapshot(persona)
        target_before_snapshot = capture_attribute_snapshot(target_persona)

        target_persona.scratch.inventory[item_name] = max(0, int(target_persona.scratch.inventory.get(item_name, 0)) - 1)
        persona.scratch.inventory[item_name] = int(persona.scratch.inventory.get(item_name, 0)) + 1
        persona.scratch.mood = max(0.0, min(100.0, float(persona.scratch.mood) - 2.0))
        target_persona.scratch.mood = max(0.0, min(100.0, float(target_persona.scratch.mood) - 18.0))

        if getattr(persona, "a_mem", None):
            persona.a_mem.update_relationship(
                target_persona.name,
                relation_type="enemy",
                trust_absolute=0.0,
                recent_event=f"robbed {item_name}",
            )
        if getattr(target_persona, "a_mem", None):
            target_persona.a_mem.update_relationship(
                persona.name,
                relation_type="enemy",
                trust_absolute=0.0,
                recent_event=f"was robbed of {item_name}",
            )

        actor_after_snapshot = capture_attribute_snapshot(persona)
        target_after_snapshot = capture_attribute_snapshot(target_persona)
        actor_effects = compute_attribute_effects(actor_before_snapshot, actor_after_snapshot)
        target_effects = compute_attribute_effects(target_before_snapshot, target_after_snapshot)

        append_debug_log(
            "skill_execution_debug.jsonl",
            {
                "persona": persona.name,
                "skill": "rob",
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
            f"{persona.name} robbed {item_name} from {target_persona.name}.",
            {"rob", "steal", "inventory_transfer", str(item_name).lower(), target_persona.name.lower()},
            actor_effects,
            poignancy=6.0,
            predicate="robbed",
            obj=target_persona.name,
        )
        record_stat_change_experience(
            target_persona,
            f"{target_persona.name} was robbed of {item_name} by {persona.name}.",
            {"robbed", "stolen", "inventory_loss", str(item_name).lower(), persona.name.lower()},
            target_effects,
            poignancy=7.0,
            predicate="lost",
            obj=persona.name,
        )

        self.finish_success(persona)
