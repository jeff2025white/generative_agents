from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.cognitive_modules.skill_packs.skill_log import append_skill_debug_log
from persona.cognitive_modules.memory_effects import (
    capture_attribute_snapshot,
    compute_attribute_effects,
    record_stat_change_experience,
)
from persona.cognitive_modules.action_target_resolver import resolve_candidate_object_address
from persona.cognitive_modules.skill_effects import build_skill_effect_spec

class RestSkillPack(BaseSkillPack):
    def __init__(self):
        super().__init__()
        self.name = "rest"
        self.associated_xp = "" # Rest doesn't have an associated skill tree XP in bootstrap
        self.effect_spec = build_skill_effect_spec(
            base_state_effects={"stamina": 40.0},
            motive_effects={},
            intent_tags=("rest", "restore_stamina", "recovery"),
        )

    def can_execute(self, persona, target, maze) -> bool:
        # 1. If currently standing on a restable object (bed/sofa/chair), they can rest immediately.
        curr_obj = maze.get_tile_path(persona.scratch.curr_tile, "game_object")
        if curr_obj:
            curr_obj_lower = curr_obj.lower()
            if any(w in curr_obj_lower for w in ["bed", "sofa", "couch", "chair", "bench"]):
                return self.set_precheck_result(True, "already_on_rest_object", {"curr_obj": curr_obj})

        # 2. Try to use the requested target if it is not "none" or empty
        if target and str(target).lower() not in ["none", "", "none target"]:
            address, _matched_target, _kind = resolve_candidate_object_address(persona, [target])
            if address is not None:
                return self.set_precheck_result(True, "rest_target_available", {"target": target, "address": address})
        
        # 3. If target is "none" or requested target is missing, try to find ANY other restable object in spatial memory
        alt_address, alt_target, _ = resolve_candidate_object_address(
            persona, ["bed", "sofa", "couch", "chair", "bench"]
        )
        if alt_address is not None:
            return self.set_precheck_result(True, "alternative_rest_target_available", {"target": alt_target, "address": alt_address})
            
        # 4. If no restable objects are found anywhere, fallback to idling in place.
        return self.set_precheck_result(True, "idle_in_place", {"curr_tile": persona.scratch.curr_tile})

    def get_target_tiles(self, persona, target, maze) -> list:
        address, _matched_target, _kind = resolve_candidate_object_address(persona, [target])
        if address and address in maze.address_tiles:
            return list(maze.address_tiles[address])
        return []

    def on_arrive(self, persona, target, maze, personas):
        self.mark_arrival_phase(persona, target=target)
        before_stamina = persona.scratch.stamina
        before_snapshot = capture_attribute_snapshot(persona)
        self.apply_declared_base_state_effects(persona)
        self.apply_declared_motive_effects(persona)
        after_snapshot = capture_attribute_snapshot(persona)
        attribute_effects = compute_attribute_effects(before_snapshot, after_snapshot)
        append_skill_debug_log(
            {
                "persona": persona.name,
                "skill": "rest",
                "event": "on_arrive_end",
                "target": target,
                "stamina_before": before_stamina,
                "stamina_after": persona.scratch.stamina,
            }
        )
        record_stat_change_experience(
            persona,
            f"{persona.name} rested at {target} and recovered stamina.",
            {"rest", "sleep", "stamina", str(target).lower()},
            attribute_effects,
            poignancy=6.0,
            predicate="changed",
            obj="rest_recovery",
        )
        self.mark_finalizing_phase(persona)
        self.finish_success(persona)
