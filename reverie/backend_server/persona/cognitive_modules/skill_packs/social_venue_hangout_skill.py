"""Leisure skill pack for intentionally hanging out at social venues."""

from persona.cognitive_modules.skill_packs.skill_log import append_skill_debug_log
from persona.cognitive_modules.memory_effects import (
    capture_attribute_snapshot,
    compute_attribute_effects,
    record_stat_change_experience,
)
from persona.cognitive_modules.skill_effects import build_skill_effect_spec
from persona.cognitive_modules.skill_packs.base import BaseSkillPack


class SocialVenueHangoutSkillPack(BaseSkillPack):
    """Go to a social venue, linger, and recover a small amount of mood."""

    def __init__(self):
        super().__init__()
        self.name = "hangout_social_venue"
        self.associated_xp = ""
        self.effect_spec = build_skill_effect_spec(
            base_state_effects={"stamina": -1.0, "mood": 2.0},
            motive_effects={"belonging": 10.0},
            intent_tags=("social", "hangout", "belonging"),
        )

    def can_execute(self, persona, target, maze) -> bool:
        return self.set_precheck_result(True, "social_venue_hangout_allowed", {"target": target})

    def get_target_tiles(self, persona, target, maze) -> list:
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        self.mark_arrival_phase(persona, target=target)
        self.update_skill_phase(persona, "settling", metadata={"target": target})
        before_snapshot = capture_attribute_snapshot(persona)
        self.apply_declared_base_state_effects(persona)
        self.apply_declared_motive_effects(persona)
        after_snapshot = capture_attribute_snapshot(persona)
        attribute_effects = compute_attribute_effects(before_snapshot, after_snapshot)
        append_skill_debug_log(
            {
                "persona": persona.name,
                "skill": self.name,
                "event": "on_arrive_end",
                "target": target,
                "stats_after": {
                    "stamina": persona.scratch.stamina,
                    "mood": persona.scratch.mood,
                    "health": persona.scratch.health,
                },
            },
        )
        record_stat_change_experience(
            persona,
            f"{persona.name} spent a while relaxing socially at {target}.",
            {"social", "hangout", str(target).lower(), "mood_recovery"},
            attribute_effects,
            poignancy=4.0,
            predicate="changed",
            obj="social_venue_hangout",
        )
        self.mark_finalizing_phase(persona, metadata={"target": target, "result": "relaxed_without_chat"})
        self.finish_success(persona)
