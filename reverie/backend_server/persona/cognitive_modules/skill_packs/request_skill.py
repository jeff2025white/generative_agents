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
from persona.cognitive_modules.skill_effects import (
    apply_base_state_effects,
    apply_declared_motive_effects,
)
from persona.cognitive_modules.skill_packs.skill_log import append_skill_debug_log


class RequestSkillPack(BaseSkillPack):
    """Ask another NPC for an immediately useful item, usually food or practical help."""

    def __init__(self):
        super().__init__()
        self.name = "request"
        self.associated_xp = ""

    def can_execute(self, persona, target, maze) -> bool:
        result = bool(str(target or "").strip())
        append_skill_debug_log(
            {
                "persona": persona.name,
                "skill": "request",
                "event": "can_execute",
                "result": result,
                "target": target,
                "inventory": dict(persona.scratch.inventory or {}),
            }
        )
        if not str(target or "").strip():
            return self.set_precheck_result(False, "target_missing", {})
        return self.set_precheck_result(True, "ready_to_request", {"target": target})

    def get_target_tiles(self, persona, target, maze) -> list:
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        self.mark_arrival_phase(persona, target=target)
        target_persona = resolve_target_persona(personas, target)
        if not target_persona:
            log_transfer_failure(persona, "request", target, "target_not_found")
            self.finish_failure(persona, "target_not_found", {"target": target})
            return
        if target_persona.name == persona.name:
            log_transfer_failure(persona, "request", target, "self_target")
            self.finish_failure(persona, "self_target", {"target": target})
            return
        if not are_personas_close(persona, target_persona):
            log_transfer_failure(
                persona,
                "request",
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
                "request",
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

        apply_base_state_effects(persona, {"mood": 1.0})
        apply_base_state_effects(target_persona, {"mood": 0.5})
        apply_declared_motive_effects(
            persona,
            skill_id="request_resource",
            motive_effects={"belonging": 2.0, "competence": 1.0},
        )
        apply_declared_motive_effects(
            target_persona,
            skill_id="request_granted",
            motive_effects={"belonging": 4.0, "status": 1.0},
        )

        if getattr(persona, "a_mem", None):
            persona.a_mem.update_relationship(
                target_persona.name,
                relation_type="friend" if persona.a_mem.get_relationship(target_persona.name) is None else None,
                trust_delta=0.08,
                recent_event=f"received requested help with {item_name}",
            )
        if getattr(target_persona, "a_mem", None):
            target_persona.a_mem.update_relationship(
                persona.name,
                relation_type="friend" if target_persona.a_mem.get_relationship(persona.name) is None else None,
                trust_delta=0.12,
                recent_event=f"received a request for {item_name} and helped",
            )

        actor_after_snapshot = capture_attribute_snapshot(persona)
        target_after_snapshot = capture_attribute_snapshot(target_persona)
        actor_effects = compute_attribute_effects(actor_before_snapshot, actor_after_snapshot)
        target_effects = compute_attribute_effects(target_before_snapshot, target_after_snapshot)

        append_skill_debug_log(
            {
                "persona": persona.name,
                "skill": "request",
                "event": "on_arrive_end",
                "target": target_persona.name,
                "item": item_name,
                "inventory_before": actor_before_inventory,
                "inventory_after": dict(persona.scratch.inventory or {}),
                "target_inventory_before": target_before_inventory,
                "target_inventory_after": dict(target_persona.scratch.inventory or {}),
                "actor_attribute_effects": actor_effects,
                "target_attribute_effects": target_effects,
            }
        )

        record_stat_change_experience(
            persona,
            f"{persona.name} requested {item_name} from {target_persona.name} and received it.",
            {"request", "resource", str(item_name).lower(), target_persona.name.lower()},
            actor_effects,
            poignancy=5.5,
            predicate="received_help_from",
            obj=target_persona.name,
        )
        record_stat_change_experience(
            target_persona,
            f"{target_persona.name} gave {item_name} to {persona.name} after being asked.",
            {"request", "helped", str(item_name).lower(), persona.name.lower()},
            target_effects,
            poignancy=4.5,
            predicate="helped",
            obj=persona.name,
        )

        self.mark_finalizing_phase(persona, metadata={"item": item_name, "target": target_persona.name})
        self.finish_success(persona)
