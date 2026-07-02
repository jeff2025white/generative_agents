"""Generic skill packs for non-survival interactions."""

from persona.cognitive_modules.action_command_utils import build_decision_signature
from persona.cognitive_modules.debug_log import append_debug_log
from persona.cognitive_modules.memory_effects import (
    capture_attribute_snapshot,
    compute_attribute_effects,
    record_stat_change_experience,
)
from persona.cognitive_modules.skill_packs.base import BaseSkillPack


class GenericActivitySkillPack(BaseSkillPack):
    """Execute generic leisure, work, study, and use interactions."""

    def __init__(self, skill_name, stat_effects=None):
        super().__init__()
        self.name = skill_name
        self.associated_xp = ""
        self.stat_effects = stat_effects or {}

    def can_execute(self, persona, target, maze) -> bool:
        next_signature = build_decision_signature(
            {"skill_id": self.name, "target": target, "source": "generic_precheck", "raw_action": self.name},
            action_address=getattr(persona.scratch, "act_address", None),
        )
        if getattr(persona.scratch, "is_recent_duplicate_action", None) and persona.scratch.is_recent_duplicate_action(next_signature, within_steps=2):
            append_debug_log(
                "skill_execution_debug.jsonl",
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
            return False
        return True

    def get_target_tiles(self, persona, target, maze) -> list:
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        before_stats = {
            "stamina": persona.scratch.stamina,
            "mood": persona.scratch.mood,
            "health": persona.scratch.health,
        }
        before_snapshot = capture_attribute_snapshot(persona)

        persona.scratch.stamina = max(
            0.0, min(100.0, persona.scratch.stamina + self.stat_effects.get("stamina", 0.0))
        )
        persona.scratch.mood = max(
            0.0, min(100.0, persona.scratch.mood + self.stat_effects.get("mood", 0.0))
        )
        persona.scratch.health = max(
            0.0, min(100.0, persona.scratch.health + self.stat_effects.get("health", 0.0))
        )
        after_snapshot = capture_attribute_snapshot(persona)
        attribute_effects = compute_attribute_effects(before_snapshot, after_snapshot)

        append_debug_log(
            "skill_execution_debug.jsonl",
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
        persona.scratch.mark_action_completed(
            action_command=persona.scratch.act_command,
            action_event=persona.scratch.act_event,
            action_description=persona.scratch.act_description,
            action_address=persona.scratch.act_address,
        )

        persona.scratch.planned_path = []
        persona.scratch.act_path_set = False
        persona.scratch.act_address = None
        persona.scratch.act_description = None
        persona.scratch.act_event = None
        persona.scratch.act_command = None
