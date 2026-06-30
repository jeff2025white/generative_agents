from persona.cognitive_modules.skill_packs.base import BaseSkillPack

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
        persona.scratch.stamina = min(100.0, persona.scratch.stamina + 40.0)
        print(f"=== [技能物理结算] {persona.name} 在 {target} 休息! 精力恢复: {persona.scratch.stamina:.1f} ===")
