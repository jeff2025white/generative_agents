from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.cognitive_modules.action_command_utils import build_action_command, build_decision_signature
from persona.cognitive_modules.action_outcomes import (
    derive_progress_score_breakdown,
)
from persona.cognitive_modules.skill_packs.skill_log import append_skill_debug_log
from persona.cognitive_modules.food_sources import (
    is_valid_gather_food_source,
    normalize_food_source_target,
)
from persona.cognitive_modules.memory_effects import (
    capture_attribute_snapshot,
    compute_attribute_effects,
    record_stat_change_experience,
)
from persona.prompt_template.gpt_structure import get_embedding

class GatherSkillPack(BaseSkillPack):
    def __init__(self):
        super().__init__()
        self.name = "gather"
        self.associated_xp = "gathering"

    def _clean_target(self, target) -> str:
        return normalize_food_source_target(target)

    def _find_available_address(self, persona, target):
        world_state = getattr(persona, "world_resource_state", None)
        candidate_addresses = []
        if getattr(persona, "s_mem", None) and hasattr(persona.s_mem, "find_all_objects"):
            candidate_addresses = persona.s_mem.find_all_objects(target)
        if not candidate_addresses:
            address = persona.s_mem.find_nearest_object(target) if getattr(persona, "s_mem", None) else None
            candidate_addresses = [address] if address else []
        for address in candidate_addresses:
            if not world_state or world_state.is_available(address):
                return address
        return candidate_addresses[0] if candidate_addresses else None

    def _record_gather_memory(self, persona, description, keywords, attribute_effects=None, poignancy=6.0):
        if not getattr(persona, "a_mem", None):
            return
        embedding = get_embedding(description)
        persona.a_mem.add_event(
            persona.scratch.curr_time,
            None,
            persona.name,
            "experienced",
            "gather_food",
            description,
            set(keywords or set()),
            float(poignancy),
            (description, embedding),
            None,
            attribute_effects=attribute_effects,
        )

    def can_execute(self, persona, target, maze) -> bool:
        clean_target = self._clean_target(target)
        world_state = getattr(persona, "world_resource_state", None)
        next_signature = build_decision_signature(
            {"skill_id": "gather", "target": clean_target, "source": "gather_precheck", "raw_action": "gather"},
            action_address=getattr(persona.scratch, "act_address", None),
        )
        if getattr(persona.scratch, "is_recent_duplicate_action", None) and persona.scratch.is_recent_duplicate_action(next_signature, within_steps=2):
            append_skill_debug_log(
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
            return self.set_precheck_result(False, "recent_duplicate_action", {"target": target, "clean_target": clean_target})
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
                append_skill_debug_log(
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
                        "satiety": float(getattr(persona.scratch, "satiety", 100.0) or 100.0),
                        "inventory": inventory,
                        "recent_completed_action_signature": recent_signature,
                    }
                )
                return self.set_precheck_result(
                    False,
                    "recent_healthy_refrigerator_gather",
                    {"target": target, "clean_target": clean_target, "curr_obj": curr_obj, "inventory": inventory},
                )
            if is_valid_gather_food_source(curr_obj_clean):
                if world_state and curr_obj_clean != "apple tree":
                    curr_address = getattr(persona.scratch, "act_address", None) or self._find_available_address(persona, curr_obj_clean)
                    if curr_address and not world_state.is_available(curr_address):
                        append_skill_debug_log(
                            {
                                "persona": persona.name,
                                "skill": "gather",
                                "event": "can_execute",
                                "result": False,
                                "reason": "resource_empty",
                                "target": target,
                                "clean_target": clean_target,
                                "curr_address": curr_address,
                            }
                        )
                        return self.set_precheck_result(
                            False,
                            "resource_empty",
                            {"target": target, "clean_target": clean_target, "curr_address": curr_address},
                        )
                append_skill_debug_log(
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
                return self.set_precheck_result(
                    True,
                    "current_object",
                    {"target": target, "clean_target": clean_target, "curr_obj": curr_obj, "curr_tile": persona.scratch.curr_tile},
                )
        if not is_valid_gather_food_source(clean_target):
            append_skill_debug_log(
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
            return self.set_precheck_result(False, "invalid_food_source", {"target": target, "clean_target": clean_target})
        # 2. Fallback: Target object must exist in spatial memory
        address = self._find_available_address(persona, clean_target)
        result = address is not None and (not world_state or world_state.is_available(address) or clean_target == "apple tree")
        append_skill_debug_log(
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
        if result:
            return self.set_precheck_result(True, "spatial_memory", {"target": target, "clean_target": clean_target, "nearest_address": address})
        failure_reason = "resource_source_missing"
        if address and world_state and not world_state.is_available(address) and clean_target != "apple tree":
            failure_reason = "resource_empty"
        return self.set_precheck_result(
            False,
            failure_reason,
            {
                "target": target,
                "clean_target": clean_target,
                "nearest_address": address,
            },
        )

    def get_target_tiles(self, persona, target, maze) -> list:
        clean_target = self._clean_target(target)
        address = self._find_available_address(persona, clean_target)
        if address and address in maze.address_tiles:
            return list(maze.address_tiles[address])
        return []

    def on_arrive(self, persona, target, maze, personas):
        self.mark_arrival_phase(persona, target=target, metadata={"curr_tile": persona.scratch.curr_tile})
        # 1. Resource output settlement
        curr_obj = maze.get_tile_path(persona.scratch.curr_tile, "game_object")
        curr_obj = curr_obj.lower() if curr_obj else ""
        before_inventory = dict(persona.scratch.inventory)
        append_skill_debug_log(
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
        source_address = getattr(persona.scratch, "act_address", None) or self._find_available_address(persona, effective_source)
        world_state = getattr(persona, "world_resource_state", None)
        self.update_skill_phase(
            persona,
            "resource_settlement",
            metadata={"effective_source": effective_source, "source_address": source_address},
        )
        if not is_valid_gather_food_source(effective_source):
            append_skill_debug_log(
                {
                    "persona": persona.name,
                    "skill": "gather",
                    "event": "on_arrive_invalid_source",
                    "target": target,
                    "curr_obj": curr_obj,
                    "inventory_before": before_inventory,
                }
            )
            self.finish_failure(
                persona,
                "gather_invalid_source",
                {
                    "target": target,
                    "curr_obj": curr_obj,
                },
            )
            return

        if world_state and effective_source != "apple tree" and source_address and not world_state.consume(source_address, amount=1):
            self._record_gather_memory(
                persona,
                f"{persona.name} found that {effective_source} at {source_address} was empty when trying to gather food.",
                {"gather", "food_source", "empty_source", effective_source, "depleted", "food"},
                attribute_effects={"satiety": 0.0, "stamina": 0.0, "health": 0.0, "mood": 0.0},
                poignancy=5.0,
            )
            append_skill_debug_log(
                {
                    "persona": persona.name,
                    "skill": "gather",
                    "event": "resource_empty_on_arrival",
                    "target": target,
                    "effective_source": effective_source,
                    "source_address": source_address,
                }
            )
            if hasattr(persona.scratch, "note_navigation_failure"):
                persona.scratch.note_navigation_failure(
                    target=effective_source,
                    target_address=source_address,
                    reason="resource_empty",
                    payload={
                        "requested_target": target,
                        "effective_source": effective_source,
                    },
                )
            self.finish_failure(
                persona,
                "resource_empty",
                {
                    "target": target,
                    "effective_source": effective_source,
                    "source_address": source_address,
                },
            )
            return

        before_snapshot = capture_attribute_snapshot(persona)
        if effective_source == "apple tree":
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 2
            persona.scratch.mood = min(100.0, persona.scratch.mood + 1.0)
        elif effective_source == "refrigerator":
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 1
        elif effective_source == "cafe counter":
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 2
        elif effective_source == "stove":
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 1
        after_snapshot = capture_attribute_snapshot(persona)
        attribute_effects = compute_attribute_effects(before_snapshot, after_snapshot)
        inventory_delta = {}
        for item, after_count in persona.scratch.inventory.items():
            before_count = before_inventory.get(item, 0)
            delta = after_count - before_count
            if delta:
                inventory_delta[item] = delta
        progress_breakdown = derive_progress_score_breakdown(
            "gather",
            self_attribute_effects=attribute_effects,
            inventory_delta=inventory_delta,
        )
        progress_score = progress_breakdown["score"]
        self._record_gather_memory(
            persona,
            f"{persona.name} gathered food from {effective_source} at {source_address or persona.scratch.act_address}.",
            {"gather", "food_source", effective_source, "food", "inventory", "apple tree" if effective_source == "apple tree" else "town_food"},
            attribute_effects=attribute_effects,
            poignancy=6.0 if effective_source != "apple tree" else 7.0,
        )
        if effective_source == "apple tree":
            record_stat_change_experience(
                persona,
                f"{persona.name} gathered apples from the apple tree and felt more optimistic about survival.",
                {"gather", "apple tree", "forage", "food", "mood_up", "reliable_source"},
                attribute_effects,
                poignancy=7.0,
                predicate="changed",
                obj="gather_recovery",
            )
        append_skill_debug_log(
            {
                "persona": persona.name,
                "skill": "gather",
                "event": "on_arrive_end",
                "target": target,
                "effective_source": effective_source,
                "source_address": source_address,
                "curr_obj": curr_obj,
                "inventory_before": before_inventory,
                "inventory_after": persona.scratch.inventory,
                "resource_stock_after": world_state.get_stock(source_address) if world_state and source_address else None,
                "attribute_effects": attribute_effects,
                "inventory_delta": inventory_delta,
                "progress_score": progress_score,
                "progress_score_breakdown": progress_breakdown,
            }
        )
        if persona.scratch.satiety < 40.0 and persona.scratch.inventory.get("apple", 0) > 0:
            followup_address = persona.scratch.act_address
            if not followup_address:
                followup_address = persona.s_mem.find_nearest_object("refrigerator") or persona.scratch.living_area
            self.update_skill_phase(
                persona,
                "followup_scheduled",
                metadata={
                    "followup_skill": "consume",
                    "followup_target": "apple",
                    "followup_address": followup_address,
                    "inventory_after": dict(persona.scratch.inventory),
                    "satiety": persona.scratch.satiety,
                },
            )
            self.mark_finalizing_phase(
                persona,
                metadata={"result": "gather_completed_with_followup_schedule"},
            )
            self.finish_success(
                persona,
                outcome_effects={
                    "self_attribute_effects": attribute_effects,
                    "inventory_delta": inventory_delta,
                    "progress_score": progress_score,
                },
            )
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
            append_skill_debug_log(
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
        self.update_skill_phase(persona, "xp_settlement")
        persona.scratch.skills[self.associated_xp]["xp"] += 10
        if persona.scratch.skills[self.associated_xp]["xp"] >= persona.scratch.skills[self.associated_xp]["level"] * 100:
            persona.scratch.skills[self.associated_xp]["level"] += 1
            persona.scratch.skills[self.associated_xp]["xp"] = 0
            append_skill_debug_log(
                {
                    "persona": persona.name,
                    "skill": "gather",
                    "event": "level_up",
                    "new_level": persona.scratch.skills[self.associated_xp]["level"],
                }
            )
            
        # Force immediate action release upon arrival to avoid duration deadlock
        self.mark_finalizing_phase(persona)
        self.finish_success(
            persona,
            outcome_effects={
                "self_attribute_effects": attribute_effects,
                "inventory_delta": inventory_delta,
                "progress_score": progress_score,
            },
        )
