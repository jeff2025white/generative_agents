from persona.cognitive_modules.skill_packs.base import BaseSkillPack

class GatherSkillPack(BaseSkillPack):
    def __init__(self):
        super().__init__()
        self.name = "gather"
        self.associated_xp = "gathering"

    def can_execute(self, persona, target, maze) -> bool:
        # 1. If currently standing on/near a source object, they can gather.
        curr_obj = maze.get_tile_path(persona.scratch.curr_tile, "game_object")
        if curr_obj:
            curr_obj_lower = curr_obj.lower()
            if any(w in curr_obj_lower for w in ["apple_tree", "tree", "refrigerator", "fridge", "cafe", "counter"]):
                return True
        # 2. Fallback: Target object must exist in spatial memory
        return persona.s_mem.find_nearest_object(target) is not None

    def get_target_tiles(self, persona, target, maze) -> list:
        address = persona.s_mem.find_nearest_object(target)
        if address and address in maze.address_tiles:
            return list(maze.address_tiles[address])
        return []

    def on_arrive(self, persona, target, maze, personas):
        # 1. Resource output settlement
        curr_obj = maze.get_tile_path(persona.scratch.curr_tile, "game_object")
        curr_obj = curr_obj.lower() if curr_obj else ""
        target_lower = target.lower()
        
        if "apple_tree" in target_lower or "tree" in target_lower or "apple_tree" in curr_obj or "tree" in curr_obj:
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 2
            print(f"=== [技能物理结算] {persona.name} 成功从苹果树采集苹果 x2! 背包: {persona.scratch.inventory} ===")
        elif "refrigerator" in target_lower or "fridge" in target_lower or "refrigerator" in curr_obj or "fridge" in curr_obj:
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 1
            print(f"=== [技能物理结算] {persona.name} 从冰箱获取了苹果 x1! 背包: {persona.scratch.inventory} ===")
        elif "cafe" in target_lower or "seating" in target_lower or "counter" in target_lower or "cafe" in curr_obj or "counter" in curr_obj:
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 2
            print(f"=== [技能物理结算] {persona.name} 在咖啡馆获取了食物 (苹果 x2)! 背包: {persona.scratch.inventory} ===")
        else:
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 1
            print(f"=== [技能物理结算] {persona.name} 采集获得了苹果 x1! 背包: {persona.scratch.inventory} ===")
        
        # 2. Skill level & XP settlement
        persona.scratch.skills[self.associated_xp]["xp"] += 10
        if persona.scratch.skills[self.associated_xp]["xp"] >= persona.scratch.skills[self.associated_xp]["level"] * 100:
            persona.scratch.skills[self.associated_xp]["level"] += 1
            persona.scratch.skills[self.associated_xp]["xp"] = 0
            print(f"=== [技能升级] {persona.name} 采集技能提升至 Lv.{persona.scratch.skills[self.associated_xp]['level']}! ===")
