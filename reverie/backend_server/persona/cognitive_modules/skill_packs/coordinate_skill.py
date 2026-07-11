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


class CoordinateSkillPack(BaseSkillPack):
    """Coordinate with another NPC for easier or more reliable execution."""

    def __init__(self):
        super().__init__()
        self.name = "coordinate"
        self.associated_xp = ""
        self.effect_spec = build_skill_effect_spec(
            base_state_effects={},
            motive_effects={"belonging": 6.0, "competence": 4.0},
            intent_tags=("coordinate", "cooperate", "team_up", "collaboration"),
        )

    def can_execute(self, persona, target, maze) -> bool:
        if not str(target or "").strip():
            return self.set_precheck_result(False, "target_missing", {})
        return self.set_precheck_result(True, "ready_to_coordinate", {"target": target})

    def get_target_tiles(self, persona, target, maze) -> list:
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        self.mark_arrival_phase(persona, target=target)
        target_persona = resolve_target_persona(personas, target)
        if not target_persona:
            log_transfer_failure(persona, "coordinate", target, "target_not_found")
            self.finish_failure(persona, "target_not_found", {"target": target})
            return
        if target_persona.name == persona.name:
            log_transfer_failure(persona, "coordinate", target, "self_target")
            self.finish_failure(persona, "self_target", {"target": target})
            return
        if not are_personas_close(persona, target_persona):
            log_transfer_failure(
                persona,
                "coordinate",
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
                relation_type="friend" if persona.a_mem.get_relationship(target_persona.name) is None else None,
                trust_delta=0.08,
                recent_event=f"coordinated with {target_persona.name}",
            )

        record_stat_change_experience(
            persona,
            f"{persona.name} coordinated with {target_persona.name} to improve execution.",
            {"coordinate", "cooperate", target_persona.name.lower(), "competence", "belonging"},
            attribute_effects,
            poignancy=5.5,
            predicate="coordinated_with",
            obj=target_persona.name,
        )
        self.mark_finalizing_phase(persona, metadata={"target": target_persona.name})
        self.finish_success(persona)
