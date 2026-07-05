from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.cognitive_modules.action_command_utils import build_decision_signature
from persona.cognitive_modules.debug_log import append_debug_log, safe_json_dumps
from persona.cognitive_modules.food_sources import normalize_food_source_target
from persona.cognitive_modules.memory_effects import (
    capture_attribute_snapshot,
    compute_attribute_effects,
    record_stat_change_experience,
)

class ConsumeSkillPack(BaseSkillPack):
    def __init__(self):
        super().__init__()
        self.name = "consume"
        self.associated_xp = "cooking"

    def can_execute(self, persona, target, maze) -> bool:
        # 1. Check if target matches an item in inventory
        normalized_target = normalize_food_source_target(target)
        item_key = normalized_target.strip().lower()
        for k in persona.scratch.inventory:
            if k.strip().lower() in item_key and persona.scratch.inventory[k] > 0:
                append_debug_log(
                    "skill_execution_debug.jsonl",
                    {
                        "persona": persona.name,
                        "skill": "consume",
                        "event": "can_execute",
                        "result": True,
                        "reason": "target_in_inventory",
                        "target": target,
                        "inventory": persona.scratch.inventory,
                    }
                )
                return True
        # 2. Fallback 1: If they have ANY consumable item in inventory, they can execute
        for k in persona.scratch.inventory:
            if persona.scratch.inventory[k] > 0:
                append_debug_log(
                    "skill_execution_debug.jsonl",
                    {
                        "persona": persona.name,
                        "skill": "consume",
                        "event": "can_execute",
                        "result": True,
                        "reason": "any_food_in_inventory",
                        "target": target,
                        "inventory": persona.scratch.inventory,
                    }
                )
                return True
        if self._is_recent_duplicate_resource_consume(persona, target):
            append_debug_log(
                "skill_execution_debug.jsonl",
                {
                    "persona": persona.name,
                    "skill": "consume",
                    "event": "can_execute",
                    "result": False,
                    "reason": "recent_duplicate_resource_consume",
                    "target": target,
                    "inventory": persona.scratch.inventory,
                    "recent_completed_action_signature": getattr(persona.scratch, "recent_completed_action_signature", None),
                    "recent_completed_action_step": getattr(persona.scratch, "recent_completed_action_step", None),
                }
            )
            return False
        curr_obj = maze.access_tile(persona.scratch.curr_tile)["game_object"] if (persona.scratch.curr_tile and maze.access_tile(persona.scratch.curr_tile)) else ""
        act_addr = normalize_food_source_target(persona.scratch.act_address).lower() if persona.scratch.act_address else ""
        append_debug_log(
            "skill_execution_debug.jsonl",
            {
                "persona": persona.name,
                "skill": "consume",
                "event": "can_execute",
                "result": False,
                "target": target,
                "inventory": persona.scratch.inventory,
                "curr_obj": curr_obj,
                "act_address": act_addr,
            }
        )
        return False

    def get_target_tiles(self, persona, target, maze) -> list:
        # Consumption can occur at current tile (no walking required if item in inventory)
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        # 1. Backpack consumption
        item_found = False
        normalized_target = normalize_food_source_target(target)
        item_key = normalized_target.strip().lower()
        target_item = target
        before_inventory = dict(persona.scratch.inventory)
        before_stats = {
            "satiety": persona.scratch.satiety,
            "health": persona.scratch.health,
            "mood": persona.scratch.mood,
        }
        append_debug_log(
            "skill_execution_debug.jsonl",
            {
                "persona": persona.name,
                "skill": "consume",
                "event": "on_arrive_start",
                "target": target,
                "curr_tile": persona.scratch.curr_tile,
                "act_address": persona.scratch.act_address,
                "inventory_before": before_inventory,
                "stats_before": before_stats,
            }
        )
        for k in list(persona.scratch.inventory.keys()):
            if k.strip().lower() in item_key and persona.scratch.inventory[k] > 0:
                persona.scratch.inventory[k] -= 1
                item_found = True
                target_item = k
                break
        
        if not item_found:
            for k in list(persona.scratch.inventory.keys()):
                if persona.scratch.inventory[k] > 0:
                    persona.scratch.inventory[k] -= 1
                    item_found = True
                    target_item = k
                    break
                    
        if not item_found:
            append_debug_log(
                "skill_execution_debug.jsonl",
                {
                    "persona": persona.name,
                    "skill": "consume",
                    "event": "on_arrive_no_food",
                    "target": target,
                    "inventory_before": before_inventory,
                    "act_address": persona.scratch.act_address,
                }
            )
            self.finish_failure(
                persona,
                "consume_no_food",
                {
                    "target": target,
                    "inventory_before": before_inventory,
                },
            )
            return
        
        # 3. Metabolic changes
        before_snapshot = capture_attribute_snapshot(persona)
        persona.scratch.satiety = min(100.0, persona.scratch.satiety + 40.0)
        persona.scratch.health = min(100.0, persona.scratch.health + 5.0)
        persona.scratch.mood = min(100.0, persona.scratch.mood + 10.0)
        after_snapshot = capture_attribute_snapshot(persona)
        attribute_effects = compute_attribute_effects(before_snapshot, after_snapshot)
        append_debug_log(
            "skill_execution_debug.jsonl",
            {
                "persona": persona.name,
                "skill": "consume",
                "event": "on_arrive_end",
                "target": target,
                "resolved_item": target_item,
                "item_found": item_found,
                "inventory_before": before_inventory,
                "inventory_after": persona.scratch.inventory,
                "stats_before": before_stats,
                "stats_after": {
                    "satiety": persona.scratch.satiety,
                    "health": persona.scratch.health,
                    "mood": persona.scratch.mood,
                },
            }
        )
        record_stat_change_experience(
            persona,
            f"{persona.name} consumed {target_item} and restored physical condition.",
            {
                "consume",
                "food",
                "meal",
                str(target_item).lower(),
                "recovery",
            },
            attribute_effects,
            poignancy=7.0,
            predicate="changed",
            obj="consume_recovery",
        )
        # 4. Cooking skill settlement
        persona.scratch.skills[self.associated_xp]["xp"] += 10
        if persona.scratch.skills[self.associated_xp]["xp"] >= persona.scratch.skills[self.associated_xp]["level"] * 100:
            persona.scratch.skills[self.associated_xp]["level"] += 1
            persona.scratch.skills[self.associated_xp]["xp"] = 0
            append_debug_log(
                "skill_execution_debug.jsonl",
                {
                    "persona": persona.name,
                    "skill": "consume",
                    "event": "level_up",
                    "new_level": persona.scratch.skills[self.associated_xp]["level"],
                }
            )
            
        # Force immediate action release upon arrival to avoid duration deadlock
        self.finish_success(persona)

    def _is_recent_duplicate_resource_consume(self, persona, target):
        inventory = getattr(persona.scratch, "inventory", {}) or {}
        if any(v > 0 for v in inventory.values()):
            return False
        recent_signature = getattr(persona.scratch, "recent_completed_action_signature", None)
        recent_step = getattr(persona.scratch, "recent_completed_action_step", None)
        curr_step = getattr(persona.scratch, "curr_step", None)
        if not recent_signature or recent_step is None or curr_step is None:
            return False
        if curr_step - recent_step > 2:
            return False
        next_signature = build_decision_signature(
            {"skill_id": "consume", "target": target, "source": "consume_precheck", "raw_action": "consume"},
            action_address=getattr(persona.scratch, "act_address", None),
        )
        return recent_signature == next_signature
            
