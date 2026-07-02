from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.cognitive_modules.action_command_utils import build_action_command, build_decision_signature
from persona.cognitive_modules.debug_log import append_debug_log, safe_json_dumps
from persona.cognitive_modules.food_sources import (
    is_valid_gather_food_source,
    normalize_food_source_target,
)

class GatherSkillPack(BaseSkillPack):
    def __init__(self):
        super().__init__()
        self.name = "gather"
        self.associated_xp = "gathering"

    def _clean_target(self, target) -> str:
        return normalize_food_source_target(target)

    def can_execute(self, persona, target, maze) -> bool:
        clean_target = self._clean_target(target)
        next_signature = build_decision_signature(
            {"skill_id": "gather", "target": clean_target, "source": "gather_precheck", "raw_action": "gather"},
            action_address=getattr(persona.scratch, "act_address", None),
        )
        if getattr(persona.scratch, "is_recent_duplicate_action", None) and persona.scratch.is_recent_duplicate_action(next_signature, within_steps=2):
            append_debug_log(
                "skill_execution_debug.jsonl",
                {
                    "persona": persona.name,
                    "skill": "gather",
                    "event": "can_execute",
                    "result": False,
                    "reason": "recent_duplicate_action",
                    "target": target,
                    "clean_target": clean_target,
                    "recent_completed_action_signature": getattr(persona.scratch, "recent_completed_action_signature", None),
                }
            )
            return False
        # 1. If currently standing on/near a source object, they can gather.
        curr_obj = maze.get_tile_path(persona.scratch.curr_tile, "game_object")
        if curr_obj:
            curr_obj_clean = self._clean_target(curr_obj)
            inventory = getattr(persona.scratch, "inventory", {}) or {}
            recent_signature = getattr(persona.scratch, "recent_completed_action_signature", None) or {}
            recent_step = getattr(persona.scratch, "recent_completed_action_step", None)
            curr_step = getattr(persona.scratch, "curr_step", None)
            satiety = float(getattr(persona.scratch, "satiety", 100.0))
            has_food_inventory = any(v > 0 for v in inventory.values())
            if (
                curr_obj_clean == "refrigerator"
                and clean_target == "refrigerator"
                and has_food_inventory
                and satiety >= 40.0
                and recent_signature.get("intent_family") == "restore_satiety"
                and recent_signature.get("skill_id") == "gather"
                and recent_signature.get("target") == "refrigerator"
                and recent_step is not None
                and curr_step is not None
                and curr_step - recent_step <= 6
            ):
                append_debug_log(
                    "skill_execution_debug.jsonl",
                    {
                        "persona": persona.name,
                        "skill": "gather",
                        "event": "can_execute",
                        "result": False,
                        "reason": "recent_healthy_refrigerator_gather",
                        "target": target,
                        "clean_target": clean_target,
                        "curr_obj": curr_obj,
                        "curr_tile": persona.scratch.curr_tile,
                        "satiety": satiety,
                        "inventory": inventory,
                        "recent_completed_action_signature": recent_signature,
                    }
                )
                return False
            if is_valid_gather_food_source(curr_obj_clean):
                append_debug_log(
                    "skill_execution_debug.jsonl",
                    {
                        "persona": persona.name,
                        "skill": "gather",
                        "event": "can_execute",
                        "result": True,
                        "reason": "current_object",
                        "target": target,
                        "clean_target": clean_target,
                        "curr_obj": curr_obj,
                        "curr_tile": persona.scratch.curr_tile,
                    }
                )
                return True
        if not is_valid_gather_food_source(clean_target):
            append_debug_log(
                "skill_execution_debug.jsonl",
                {
                    "persona": persona.name,
                    "skill": "gather",
                    "event": "can_execute",
                    "result": False,
                    "reason": "invalid_food_source",
                    "target": target,
                    "clean_target": clean_target,
                    "curr_obj": curr_obj,
                }
            )
            return False
        # 2. Fallback: Target object must exist in spatial memory
        address = persona.s_mem.find_nearest_object(clean_target)
        result = address is not None
        append_debug_log(
            "skill_execution_debug.jsonl",
            {
                "persona": persona.name,
                "skill": "gather",
                "event": "can_execute",
                "result": result,
                "reason": "spatial_memory",
                "target": target,
                "clean_target": clean_target,
                "curr_obj": curr_obj,
                "nearest_address": address,
            }
        )
        return result

    def get_target_tiles(self, persona, target, maze) -> list:
        clean_target = self._clean_target(target)
        address = persona.s_mem.find_nearest_object(clean_target)
        if address and address in maze.address_tiles:
            return list(maze.address_tiles[address])
        return []

    def on_arrive(self, persona, target, maze, personas):
        # 1. Resource output settlement
        curr_obj = maze.get_tile_path(persona.scratch.curr_tile, "game_object")
        curr_obj = curr_obj.lower() if curr_obj else ""
        before_inventory = dict(persona.scratch.inventory)
        append_debug_log(
            "skill_execution_debug.jsonl",
            {
                "persona": persona.name,
                "skill": "gather",
                "event": "on_arrive_start",
                "target": target,
                "curr_obj": curr_obj,
                "curr_tile": persona.scratch.curr_tile,
                "inventory_before": before_inventory,
                "act_address": persona.scratch.act_address,
                "act_event": persona.scratch.act_event,
                "act_command": persona.scratch.act_command,
            }
        )
        
        effective_source = self._clean_target(target) if is_valid_gather_food_source(target) else self._clean_target(curr_obj)
        if not is_valid_gather_food_source(effective_source):
            append_debug_log(
                "skill_execution_debug.jsonl",
                {
                    "persona": persona.name,
                    "skill": "gather",
                    "event": "on_arrive_invalid_source",
                    "target": target,
                    "curr_obj": curr_obj,
                    "inventory_before": before_inventory,
                }
            )
            persona.scratch.planned_path = []
            persona.scratch.act_path_set = False
            persona.scratch.act_address = None
            persona.scratch.act_description = None
            persona.scratch.act_event = None
            persona.scratch.act_command = None
            return

        if effective_source == "apple tree":
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 2
        elif effective_source == "refrigerator":
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 1
        elif effective_source == "cafe counter":
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 2
        elif effective_source == "stove":
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 1
        append_debug_log(
            "skill_execution_debug.jsonl",
            {
                "persona": persona.name,
                "skill": "gather",
                "event": "on_arrive_end",
                "target": target,
                "effective_source": effective_source,
                "curr_obj": curr_obj,
                "inventory_before": before_inventory,
                "inventory_after": persona.scratch.inventory,
            }
        )
        persona.scratch.mark_action_completed(
            action_command=persona.scratch.act_command,
            action_event=persona.scratch.act_event,
            action_description=persona.scratch.act_description,
            action_address=persona.scratch.act_address,
        )

        if persona.scratch.satiety < 40.0 and persona.scratch.inventory.get("apple", 0) > 0:
            followup_address = persona.scratch.act_address
            if not followup_address:
                followup_address = persona.s_mem.find_nearest_object("refrigerator") or persona.scratch.living_area
            persona.scratch.add_new_action(
                followup_address,
                2,
                "eating the apple from inventory to restore satiety",
                "🍎",
                (persona.name, "consume", "apple"),
                build_action_command("consume", "apple", source="post_gather_followup", raw_action="consume"),
                None,
                None,
                {},
                None,
                "being eaten by %s" % persona.scratch.first_name,
                "🍽️",
                ("apple", "consumed_by", persona.name),
                persona.scratch.curr_time
            )
            append_debug_log(
                "skill_execution_debug.jsonl",
                {
                    "persona": persona.name,
                    "skill": "gather",
                    "event": "followup_consume_scheduled",
                    "followup_address": followup_address,
                    "inventory_after": persona.scratch.inventory,
                    "satiety": persona.scratch.satiety,
                }
            )
            return
        
        # 2. Skill level & XP settlement
        persona.scratch.skills[self.associated_xp]["xp"] += 10
        if persona.scratch.skills[self.associated_xp]["xp"] >= persona.scratch.skills[self.associated_xp]["level"] * 100:
            persona.scratch.skills[self.associated_xp]["level"] += 1
            persona.scratch.skills[self.associated_xp]["xp"] = 0
            append_debug_log(
                "skill_execution_debug.jsonl",
                {
                    "persona": persona.name,
                    "skill": "gather",
                    "event": "level_up",
                    "new_level": persona.scratch.skills[self.associated_xp]["level"],
                }
            )
            
        # Force immediate action release upon arrival to avoid duration deadlock
        persona.scratch.planned_path = []
        persona.scratch.act_path_set = False
        persona.scratch.act_address = None
        persona.scratch.act_description = None
        persona.scratch.act_event = None
        persona.scratch.act_command = None
