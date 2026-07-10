from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.cognitive_modules.memory_effects import (
    capture_attribute_snapshot,
    compute_attribute_effects,
    record_stat_change_experience,
)
from persona.cognitive_modules.skill_effects import build_skill_effect_spec


class CollectiveWorshipSkillPack(BaseSkillPack):
    """NPC participates in collective worship at Johnson Park's apple tree or Town Square."""

    def __init__(self):
        super().__init__()
        self.name = "collective_worship"
        self.associated_xp = ""
        self.effect_spec = build_skill_effect_spec(
            base_state_effects={},
            motive_effects={"belonging": 20.0},
            intent_tags=("worship", "pray", "belonging", "recovery"),
        )

    def can_execute(self, persona, target, maze) -> bool:
        return self.set_precheck_result(True, "worship_allowed", {"target": target})

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
            f"{persona.name} participated in collective worship at {target}.",
            {"worship", "pray", str(target).lower(), "belonging"},
            attribute_effects,
            poignancy=7.0,
            predicate="worshipped",
            obj=str(target),
        )
        self.mark_finalizing_phase(persona)
        self.finish_success(persona)
