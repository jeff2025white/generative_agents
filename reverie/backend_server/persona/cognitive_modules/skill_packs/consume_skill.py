from persona.cognitive_modules.skill_packs.base import BaseSkillPack

class ConsumeSkillPack(BaseSkillPack):
    def __init__(self):
        super().__init__()
        self.name = "consume"
        self.associated_xp = "cooking"

    def can_execute(self, persona, target, maze) -> bool:
        # 1. Check if target matches an item in inventory
        item_key = target.strip().lower()
        for k in persona.scratch.inventory:
            if k.strip().lower() in item_key and persona.scratch.inventory[k] > 0:
                return True
        # 2. Fallback: If they have ANY consumable item in inventory, they can execute
        for k in persona.scratch.inventory:
            if persona.scratch.inventory[k] > 0:
                return True
        return False

    def get_target_tiles(self, persona, target, maze) -> list:
        # Consumption can occur at current tile (no walking required if item in inventory)
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        # 1. Backpack consumption
        item_found = False
        item_key = target.strip().lower()
        target_item = target
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
        
        # 2. Metabolic changes
        persona.scratch.satiety = min(100.0, persona.scratch.satiety + 40.0)
        persona.scratch.health = min(100.0, persona.scratch.health + 5.0)
        persona.scratch.mood = min(100.0, persona.scratch.mood + 10.0)
        print(f"=== [技能物理结算] {persona.name} 食用了 {target_item if item_found else target}! 饱食度: {persona.scratch.satiety:.1f}, 生命值: {persona.scratch.health:.1f}, 情绪值: {persona.scratch.mood:.1f} ===")
        
        # 3. Cooking skill settlement
        persona.scratch.skills[self.associated_xp]["xp"] += 10
        if persona.scratch.skills[self.associated_xp]["xp"] >= persona.scratch.skills[self.associated_xp]["level"] * 100:
            persona.scratch.skills[self.associated_xp]["level"] += 1
            persona.scratch.skills[self.associated_xp]["xp"] = 0
            print(f"=== [技能升级] {persona.name} 烹饪技能提升至 Lv.{persona.scratch.skills[self.associated_xp]['level']}! ===")
