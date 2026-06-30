from persona.cognitive_modules.skill_packs.base import BaseSkillPack

class SingingSkillPack(BaseSkillPack):
    def __init__(self):
        super().__init__()
        self.name = "sing"
        self.associated_xp = "singing"

    def can_execute(self, persona, target, maze) -> bool:
        # Singing can be executed anywhere without physical checks
        return True

    def get_target_tiles(self, persona, target, maze) -> list:
        # Singing occurs in place
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        # 1. Restore Stamina and Mood as singing boosts happiness
        persona.scratch.stamina = min(100.0, persona.scratch.stamina + 5.0)
        persona.scratch.mood = min(100.0, persona.scratch.mood + 15.0)
        print(f"=== [技能物理结算] {persona.name} 唱了一首歌! 精力值恢复至: {persona.scratch.stamina:.1f}, 情绪值恢复至: {persona.scratch.mood:.1f} ===")

        # 2. Skill level & XP settlement
        if self.associated_xp in persona.scratch.skills:
            persona.scratch.skills[self.associated_xp]["xp"] += 10
            if persona.scratch.skills[self.associated_xp]["xp"] >= persona.scratch.skills[self.associated_xp]["level"] * 100:
                persona.scratch.skills[self.associated_xp]["level"] += 1
                persona.scratch.skills[self.associated_xp]["xp"] = 0
                print(f"=== [技能升级] {persona.name} 唱歌技能提升至 Lv.{persona.scratch.skills[self.associated_xp]['level']}! ===")
