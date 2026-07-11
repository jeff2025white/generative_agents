from persona.cognitive_modules.memory_effects import (
    capture_attribute_snapshot,
    compute_attribute_effects,
    record_stat_change_experience,
)
from persona.cognitive_modules.skill_effects import build_skill_effect_spec
from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.cognitive_modules.skill_packs.transfer_skill_utils import (
    are_personas_close,
    log_transfer_failure,
    resolve_target_persona,
)


class PressureSkillPack(BaseSkillPack):
    """Pressure another NPC to comply when softer methods feel too weak."""

    def __init__(self):
        super().__init__()
        self.name = "pressure"
        self.associated_xp = ""
        self.effect_spec = build_skill_effect_spec(
            base_state_effects={"mood": -3.0},
            motive_effects={"autonomy": 5.0, "belonging": -6.0},
            intent_tags=("pressure", "demand", "corner", "assert_control"),
        )

    def can_execute(self, persona, target, maze) -> bool:
        if not str(target or "").strip():
            return self.set_precheck_result(False, "target_missing", {})
        return self.set_precheck_result(True, "ready_to_pressure", {"target": target})

    def get_target_tiles(self, persona, target, maze) -> list:
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        self.mark_arrival_phase(persona, target=target)
        target_persona = resolve_target_persona(personas, target)
        if not target_persona:
            log_transfer_failure(persona, "pressure", target, "target_not_found")
            self.finish_failure(persona, "target_not_found", {"target": target})
            return
        if target_persona.name == persona.name:
            log_transfer_failure(persona, "pressure", target, "self_target")
            self.finish_failure(persona, "self_target", {"target": target})
            return
        if not are_personas_close(persona, target_persona):
            log_transfer_failure(
                persona,
                "pressure",
                target,
                "target_not_close",
                extra={"target_tile": getattr(target_persona.scratch, "curr_tile", None)},
            )
            self.finish_failure(
                persona,
                "target_not_close",
                {"target": target, "target_tile": getattr(target_persona.scratch, "curr_tile", None)},
            )
            return

        before_snapshot = capture_attribute_snapshot(persona)
        self.apply_declared_base_state_effects(persona)
        self.apply_declared_motive_effects(persona)
        after_snapshot = capture_attribute_snapshot(persona)
        attribute_effects = compute_attribute_effects(before_snapshot, after_snapshot)

        if getattr(persona, "a_mem", None):
            persona.a_mem.update_relationship(
                target_persona.name,
                relation_type="enemy",
                trust_absolute=0.1,
                recent_event=f"pressured {target_persona.name} to comply",
            )

        record_stat_change_experience(
            persona,
            f"{persona.name} pressured {target_persona.name} to comply.",
            {"pressure", "demand", target_persona.name.lower(), "autonomy", "belonging"},
            attribute_effects,
            poignancy=6.0,
            predicate="pressured",
            obj=target_persona.name,
        )
        self.mark_finalizing_phase(persona, metadata={"target": target_persona.name})
        self.finish_success(persona)
