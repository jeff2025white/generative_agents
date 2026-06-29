from persona.cognitive_modules.skill_packs.base import BaseSkillPack

class GatherSkillPack(BaseSkillPack):
    def __init__(self):
        super().__init__()
        self.name = "gather"
        self.associated_xp = "gathering"

    def can_execute(self, persona, target, maze) -> bool:
        # Physical check: Target object must exist in persona's spatial memory
        return persona.s_mem.find_nearest_object(target) is not None

    def get_target_tiles(self, persona, target, maze) -> list:
        address = persona.s_mem.find_nearest_object(target)
        if address and address in maze.address_tiles:
            return list(maze.address_tiles[address])
        return []

    def on_arrive(self, persona, target, maze, personas):
        # 1. Resource output settlement
        if "apple_tree" in target.lower():
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 2
            print(f"=== [技能物理结算] {persona.name} 成功从苹果树采集苹果 x2! 背包: {persona.scratch.inventory} ===")
        elif "refrigerator" in target.lower() or "fridge" in target.lower():
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 1
            print(f"=== [技能物理结算] {persona.name} 从冰箱获取了苹果 x1! 背包: {persona.scratch.inventory} ===")
        elif "cafe" in target.lower() or "seating" in target.lower() or "counter" in target.lower():
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 2
            print(f"=== [技能物理结算] {persona.name} 在咖啡馆获取了食物 (苹果 x2)! 背包: {persona.scratch.inventory} ===")
        
        # 2. Skill level & XP settlement
        persona.scratch.skills[self.associated_xp]["xp"] += 10
        if persona.scratch.skills[self.associated_xp]["xp"] >= persona.scratch.skills[self.associated_xp]["level"] * 100:
            persona.scratch.skills[self.associated_xp]["level"] += 1
            persona.scratch.skills[self.associated_xp]["xp"] = 0
            print(f"=== [技能升级] {persona.name} 采集技能提升至 Lv.{persona.scratch.skills[self.associated_xp]['level']}! ===")
