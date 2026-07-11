from persona.cognitive_modules.memory_effects import (
    capture_attribute_snapshot,
    compute_attribute_effects,
    record_stat_change_experience,
)
from persona.cognitive_modules.skill_effects import build_skill_effect_spec
from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.cognitive_modules.skill_packs.transfer_skill_utils import resolve_target_persona


class AvoidSkillPack(BaseSkillPack):
    """Disengage from a risky person to regain safety and conserve energy."""

    def __init__(self):
        super().__init__()
        self.name = "avoid"
        self.associated_xp = ""
        self.effect_spec = build_skill_effect_spec(
            base_state_effects={"stamina": 2.0},
            motive_effects={"safety": 6.0},
            intent_tags=("avoid", "bypass", "disengage", "leave", "safety"),
        )

    def can_execute(self, persona, target, maze) -> bool:
        if not str(target or "").strip():
            return self.set_precheck_result(False, "target_missing", {})
        return self.set_precheck_result(True, "ready_to_avoid", {"target": target})

    def get_target_tiles(self, persona, target, maze) -> list:
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        self.mark_arrival_phase(persona, target=target)
        target_persona = resolve_target_persona(personas, target)
        target_name = target_persona.name if target_persona else str(target)

        before_snapshot = capture_attribute_snapshot(persona)
        self.apply_declared_base_state_effects(persona)
        self.apply_declared_motive_effects(persona)
        after_snapshot = capture_attribute_snapshot(persona)
        attribute_effects = compute_attribute_effects(before_snapshot, after_snapshot)

        if getattr(persona, "a_mem", None) and target_persona:
            persona.a_mem.update_relationship(
                target_persona.name,
                relation_type=None,
                trust_delta=-0.04,
                recent_event=f"avoided {target_persona.name}",
            )

        record_stat_change_experience(
            persona,
            f"{persona.name} avoided {target_name} to stay safe and keep distance.",
            {"avoid", "disengage", str(target_name).lower(), "safety"},
            attribute_effects,
            poignancy=4.5,
            predicate="avoided",
            obj=str(target_name),
        )
        self.mark_finalizing_phase(persona, metadata={"target": target_name})
        self.finish_success(persona)
