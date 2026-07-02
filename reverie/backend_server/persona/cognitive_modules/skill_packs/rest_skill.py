from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.cognitive_modules.debug_log import append_debug_log, safe_json_dumps
from persona.cognitive_modules.memory_effects import (
    capture_attribute_snapshot,
    compute_attribute_effects,
    record_stat_change_experience,
)

class RestSkillPack(BaseSkillPack):
    def __init__(self):
        super().__init__()
        self.name = "rest"
        self.associated_xp = "" # Rest doesn't have an associated skill tree XP in bootstrap

    def can_execute(self, persona, target, maze) -> bool:
        # 1. If currently standing on a restable object (bed/sofa/chair), they can rest.
        curr_obj = maze.get_tile_path(persona.scratch.curr_tile, "game_object")
        if curr_obj:
            curr_obj_lower = curr_obj.lower()
            if any(w in curr_obj_lower for w in ["bed", "sofa", "couch", "chair", "bench"]):
                return True
        # 2. Fallback: Target object must exist in spatial memory
        return persona.s_mem.find_nearest_object(target) is not None

    def get_target_tiles(self, persona, target, maze) -> list:
        address = persona.s_mem.find_nearest_object(target)
        if address and address in maze.address_tiles:
            return list(maze.address_tiles[address])
        return []

    def on_arrive(self, persona, target, maze, personas):
        # 1. Metabolism stamina recovery
        before_stamina = persona.scratch.stamina
        completed_command = persona.scratch.act_command
        completed_event = persona.scratch.act_event
        completed_description = persona.scratch.act_description
        completed_address = persona.scratch.act_address
        before_snapshot = capture_attribute_snapshot(persona)
        persona.scratch.stamina = min(100.0, persona.scratch.stamina + 40.0)
        after_snapshot = capture_attribute_snapshot(persona)
        attribute_effects = compute_attribute_effects(before_snapshot, after_snapshot)
        append_debug_log(
            "skill_execution_debug.jsonl",
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
        persona.scratch.mark_action_completed(
            action_command=completed_command,
            action_event=completed_event,
            action_description=completed_description,
            action_address=completed_address,
        )
        persona.scratch.planned_path = []
        persona.scratch.act_path_set = False
        persona.scratch.act_address = None
        persona.scratch.act_description = None
        persona.scratch.act_event = None
        persona.scratch.act_command = None
