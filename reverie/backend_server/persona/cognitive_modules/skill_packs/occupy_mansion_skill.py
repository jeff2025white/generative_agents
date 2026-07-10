from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.cognitive_modules.memory_effects import (
    capture_attribute_snapshot,
    compute_attribute_effects,
    record_stat_change_experience,
)
from persona.cognitive_modules.skill_effects import build_skill_effect_spec


class OccupyMansionSkillPack(BaseSkillPack):
    """NPC claims and occupies a mansion space or sofa to boost status."""

    def __init__(self):
        super().__init__()
        self.name = "occupy_mansion"
        self.associated_xp = ""
        self.effect_spec = build_skill_effect_spec(
            base_state_effects={},
            motive_effects={"status": 30.0},
            intent_tags=("occupy", "claim", "status", "recovery"),
        )

    def can_execute(self, persona, target, maze) -> bool:
        return self.set_precheck_result(True, "occupy_allowed", {"target": target})

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
            f"{persona.name} claimed and occupied {target}.",
            {"occupy", "claim", str(target).lower(), "status"},
            attribute_effects,
            poignancy=6.0,
            predicate="claimed",
            obj=str(target),
        )
        self.mark_finalizing_phase(persona)
        self.finish_success(persona)
