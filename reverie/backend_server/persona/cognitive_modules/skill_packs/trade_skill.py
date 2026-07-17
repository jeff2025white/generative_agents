from persona.cognitive_modules.memory_effects import (
    capture_attribute_snapshot,
    compute_attribute_effects,
    record_stat_change_experience,
)
from persona.cognitive_modules.action_outcomes import derive_progress_score
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


class TradeSkillPack(BaseSkillPack):
    """Exchange an item or future favor with another NPC for a needed resource."""

    def __init__(self):
        super().__init__()
        self.name = "trade"
        self.associated_xp = ""

    def can_execute(self, persona, target, maze) -> bool:
        result = bool(str(target or "").strip())
        append_skill_debug_log(
            {
                "persona": persona.name,
                "skill": "trade",
                "event": "can_execute",
                "result": result,
                "target": target,
                "inventory": dict(persona.scratch.inventory or {}),
            }
        )
        if not str(target or "").strip():
            return self.set_precheck_result(False, "target_missing", {})
        return self.set_precheck_result(True, "ready_to_trade", {"target": target})

    def get_target_tiles(self, persona, target, maze) -> list:
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        self.mark_arrival_phase(persona, target=target)
        target_persona = resolve_target_persona(personas, target)
        if not target_persona:
            log_transfer_failure(persona, "trade", target, "target_not_found")
            self.finish_failure(persona, "target_not_found", {"target": target})
            return
        if target_persona.name == persona.name:
            log_transfer_failure(persona, "trade", target, "self_target")
            self.finish_failure(persona, "self_target", {"target": target})
            return
        if not are_personas_close(persona, target_persona):
            log_transfer_failure(
                persona,
                "trade",
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
        requested_item = choose_inventory_item(target_persona.scratch.inventory, hint_text=detail_hint)
        if not requested_item:
            log_transfer_failure(
                persona,
                "trade",
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

        offered_item = choose_inventory_item(persona.scratch.inventory, hint_text=detail_hint)

        actor_before_inventory = dict(persona.scratch.inventory or {})
        target_before_inventory = dict(target_persona.scratch.inventory or {})
        actor_before_snapshot = capture_attribute_snapshot(persona)
        target_before_snapshot = capture_attribute_snapshot(target_persona)

        target_persona.scratch.inventory[requested_item] = max(0, int(target_persona.scratch.inventory.get(requested_item, 0)) - 1)
        persona.scratch.inventory[requested_item] = int(persona.scratch.inventory.get(requested_item, 0)) + 1

        if offered_item:
            persona.scratch.inventory[offered_item] = max(0, int(persona.scratch.inventory.get(offered_item, 0)) - 1)
            target_persona.scratch.inventory[offered_item] = int(target_persona.scratch.inventory.get(offered_item, 0)) + 1

        # If the actor has nothing in inventory, treat the trade as a promised future favor.
        apply_base_state_effects(persona, {"mood": 1.0})
        apply_base_state_effects(target_persona, {"mood": 0.5})
        apply_declared_motive_effects(
            persona,
            skill_id="trade_resource",
            motive_effects={"autonomy": 2.0, "competence": 2.0},
        )
        apply_declared_motive_effects(
            target_persona,
            skill_id="trade_partner",
            motive_effects={"status": 1.0, "belonging": 2.0},
        )

        if getattr(persona, "a_mem", None):
            persona.a_mem.update_relationship(
                target_persona.name,
                relation_type="friend" if persona.a_mem.get_relationship(target_persona.name) is None else None,
                trust_delta=0.06,
                recent_event=f"traded for {requested_item}",
            )
        if getattr(target_persona, "a_mem", None):
            target_persona.a_mem.update_relationship(
                persona.name,
                relation_type="friend" if target_persona.a_mem.get_relationship(persona.name) is None else None,
                trust_delta=0.06,
                recent_event=(
                    f"traded {requested_item} for {offered_item}"
                    if offered_item
                    else f"traded {requested_item} for a future favor"
                ),
            )

        actor_after_snapshot = capture_attribute_snapshot(persona)
        target_after_snapshot = capture_attribute_snapshot(target_persona)
        actor_effects = compute_attribute_effects(actor_before_snapshot, actor_after_snapshot)
        target_effects = compute_attribute_effects(target_before_snapshot, target_after_snapshot)

        append_skill_debug_log(
            {
                "persona": persona.name,
                "skill": "trade",
                "event": "on_arrive_end",
                "target": target_persona.name,
                "requested_item": requested_item,
                "offered_item": offered_item,
                "inventory_before": actor_before_inventory,
                "inventory_after": dict(persona.scratch.inventory or {}),
                "target_inventory_before": target_before_inventory,
                "target_inventory_after": dict(target_persona.scratch.inventory or {}),
                "actor_attribute_effects": actor_effects,
                "target_attribute_effects": target_effects,
            }
        )

        actor_trade_text = (
            f"{persona.name} traded {offered_item} with {target_persona.name} for {requested_item}."
            if offered_item
            else f"{persona.name} negotiated a future favor with {target_persona.name} and received {requested_item}."
        )
        target_trade_text = (
            f"{target_persona.name} traded {requested_item} with {persona.name} for {offered_item}."
            if offered_item
            else f"{target_persona.name} gave {requested_item} to {persona.name} in exchange for a future favor."
        )

        record_stat_change_experience(
            persona,
            actor_trade_text,
            {"trade", "resource", str(requested_item).lower(), target_persona.name.lower()},
            actor_effects,
            poignancy=5.5,
            predicate="traded_with",
            obj=target_persona.name,
        )
        record_stat_change_experience(
            target_persona,
            target_trade_text,
            {"trade", "resource", str(requested_item).lower(), persona.name.lower()},
            target_effects,
            poignancy=4.5,
            predicate="traded_with",
            obj=persona.name,
        )

        self.mark_finalizing_phase(
            persona,
            metadata={"item": requested_item, "offered_item": offered_item, "target": target_persona.name},
        )
        inventory_delta = {
            item: int(persona.scratch.inventory.get(item, 0)) - int(actor_before_inventory.get(item, 0))
            for item in set(actor_before_inventory) | set(persona.scratch.inventory or {})
        }
        inventory_delta = {item: delta for item, delta in inventory_delta.items() if delta}
        self.finish_success(
            persona,
            outcome_effects={
                "self_attribute_effects": actor_effects,
                "inventory_delta": inventory_delta,
                "progress_score": derive_progress_score(
                    "trade",
                    self_attribute_effects=actor_effects,
                    inventory_delta=inventory_delta,
                ),
            },
        )
