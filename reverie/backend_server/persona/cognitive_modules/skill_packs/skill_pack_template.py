"""
Template for adding a new Persona skill pack.

Copy this file, rename the class and registry entry, then implement the
domain-specific logic. Do not manually clear scratch action fields inside
skill code. Always terminate with one of:

- self.finish_success(persona)
- self.finish_failure(persona, "reason_code", payload={...})
- self.finish_interrupted(persona, "reason_code", payload={...})
"""

from persona.cognitive_modules.skill_packs.base import BaseSkillPack


class TemplateSkillPack(BaseSkillPack):
    def __init__(self):
        super().__init__()
        self.name = "template_skill"
        self.associated_xp = ""

    def can_execute(self, persona, target, maze) -> bool:
        """
        Return True when the physical prerequisites are satisfied.
        """
        return True

    def get_target_tiles(self, persona, target, maze) -> list:
        """
        Return candidate tiles for execution.
        Most in-place actions can simply return [persona.scratch.curr_tile].
        """
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        """
        Apply inventory/stat/memory side effects, then terminate through a
        BaseSkillPack finish_* helper.
        """
        if not target:
            self.finish_failure(
                persona,
                "missing_target",
                payload={"target": target},
            )
            return

        # Do work here.
        # Example:
        # persona.scratch.mood = min(100.0, persona.scratch.mood + 5.0)

        self.finish_success(persona)
