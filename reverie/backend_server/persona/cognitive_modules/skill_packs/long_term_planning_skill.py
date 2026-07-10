from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.cognitive_modules.memory_effects import (
    capture_attribute_snapshot,
    compute_attribute_effects,
    record_stat_change_experience,
)
from persona.cognitive_modules.skill_effects import build_skill_effect_spec


class LongTermPlanningSkillPack(BaseSkillPack):
    """NPC makes micro-plans or schedules on desks to regain meaning/order."""

    def __init__(self):
        super().__init__()
        self.name = "long_term_planning"
        self.associated_xp = ""
        self.effect_spec = build_skill_effect_spec(
            base_state_effects={},
            motive_effects={"meaning": 20.0},
            intent_tags=("plan", "planning", "micro-planning", "meaning", "recovery"),
        )

    def can_execute(self, persona, target, maze) -> bool:
        return self.set_precheck_result(True, "planning_allowed", {"target": target})

    def get_target_tiles(self, persona, target, maze) -> list:
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        self.mark_arrival_phase(persona, target=target)
        before_snapshot = capture_attribute_snapshot(persona)

        self.apply_declared_base_state_effects(persona)
        self.apply_declared_motive_effects(persona)

        after_snapshot = capture_attribute_snapshot(persona)
        attribute_effects = compute_attribute_effects(before_snapshot, after_snapshot)

        record_stat_change_experience(
            persona,
            f"{persona.name} made micro-plans at {target} to restore order.",
            {"plan", "planning", str(target).lower(), "meaning"},
            attribute_effects,
            poignancy=6.0,
            predicate="planned",
            obj=str(target),
        )
        self.mark_finalizing_phase(persona)
        self.finish_success(persona)
