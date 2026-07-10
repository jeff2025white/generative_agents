"""Generic skill packs for non-survival interactions."""

from persona.cognitive_modules.action_command_utils import build_decision_signature
from persona.cognitive_modules.skill_packs.skill_log import append_skill_debug_log
from persona.cognitive_modules.memory_effects import (
    capture_attribute_snapshot,
    compute_attribute_effects,
    record_stat_change_experience,
)
from persona.cognitive_modules.skill_effects import build_skill_effect_spec
from persona.cognitive_modules.skill_packs.base import BaseSkillPack


class GenericActivitySkillPack(BaseSkillPack):
    """Execute generic leisure, work, study, and use interactions."""

    def __init__(self, skill_name, stat_effects=None, motive_effects=None):
        super().__init__()
        self.name = skill_name
        self.associated_xp = ""
        self.stat_effects = stat_effects or {}
        self.effect_spec = build_skill_effect_spec(
            base_state_effects=self.stat_effects,
            motive_effects=motive_effects,
            intent_tags=(skill_name,),
        )

    def can_execute(self, persona, target, maze) -> bool:
        next_signature = build_decision_signature(
            {"skill_id": self.name, "target": target, "source": "generic_precheck", "raw_action": self.name},
            action_address=getattr(persona.scratch, "act_address", None),
        )
        if getattr(persona.scratch, "is_recent_duplicate_action", None) and persona.scratch.is_recent_duplicate_action(next_signature, within_steps=2):
            append_skill_debug_log(
                {
                    "persona": persona.name,
                    "skill": self.name,
                    "event": "can_execute",
                    "result": False,
                    "reason": "recent_duplicate_action",
                    "target": target,
                    "recent_completed_action_signature": getattr(persona.scratch, "recent_completed_action_signature", None),
                },
            )
            return self.set_precheck_result(False, "recent_duplicate_action", {"target": target})
        return self.set_precheck_result(True, "generic_activity_allowed", {"target": target})

    def get_target_tiles(self, persona, target, maze) -> list:
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        self.mark_arrival_phase(persona, target=target)
        before_stats = {
            "stamina": persona.scratch.stamina,
            "mood": persona.scratch.mood,
            "health": persona.scratch.health,
        }
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
                "stats_before": before_stats,
                "stats_after": {
                    "stamina": persona.scratch.stamina,
                    "mood": persona.scratch.mood,
                    "health": persona.scratch.health,
                },
            },
        )
        record_stat_change_experience(
            persona,
            f"{persona.name} spent time on {self.name} with target {target}.",
            {self.name, str(target).lower(), "activity"},
            attribute_effects,
            poignancy=5.0,
            predicate="changed",
            obj=f"{self.name}_activity",
        )
        self.mark_finalizing_phase(persona)
        self.finish_success(persona)
