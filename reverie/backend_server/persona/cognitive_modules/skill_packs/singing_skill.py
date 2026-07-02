from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.cognitive_modules.debug_log import append_debug_log
from persona.cognitive_modules.memory_effects import (
    capture_attribute_snapshot,
    compute_attribute_effects,
    record_stat_change_experience,
)

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
        before_stamina = persona.scratch.stamina
        before_mood = persona.scratch.mood
        before_snapshot = capture_attribute_snapshot(persona)
        persona.scratch.stamina = min(100.0, persona.scratch.stamina + 5.0)
        persona.scratch.mood = min(100.0, persona.scratch.mood + 15.0)
        after_snapshot = capture_attribute_snapshot(persona)
        attribute_effects = compute_attribute_effects(before_snapshot, after_snapshot)
        append_debug_log(
            "skill_execution_debug.jsonl",
            {
                "persona": persona.name,
                "skill": "sing",
                "event": "on_arrive_end",
                "stamina_before": before_stamina,
                "stamina_after": persona.scratch.stamina,
                "mood_before": before_mood,
                "mood_after": persona.scratch.mood,
            }
        )
        record_stat_change_experience(
            persona,
            f"{persona.name} sang for a while and felt more energetic and upbeat.",
            {"sing", "music", "stamina", "mood", "recovery"},
            attribute_effects,
            poignancy=6.0,
            predicate="changed",
            obj="sing_recovery",
        )

        # 2. Skill level & XP settlement
        if self.associated_xp in persona.scratch.skills:
            persona.scratch.skills[self.associated_xp]["xp"] += 10
            if persona.scratch.skills[self.associated_xp]["xp"] >= persona.scratch.skills[self.associated_xp]["level"] * 100:
                persona.scratch.skills[self.associated_xp]["level"] += 1
                persona.scratch.skills[self.associated_xp]["xp"] = 0
                append_debug_log(
                    "skill_execution_debug.jsonl",
                    {
                        "persona": persona.name,
                        "skill": "sing",
                        "event": "level_up",
                        "new_level": persona.scratch.skills[self.associated_xp]["level"],
                    }
                )
