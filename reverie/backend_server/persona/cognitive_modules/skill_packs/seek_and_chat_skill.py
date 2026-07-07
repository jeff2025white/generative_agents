"""Skill pack for explicitly seeking out a persona and then starting chat."""

from persona.cognitive_modules.social_dialogue_log import build_dialogue_id, log_social_dialogue, set_social_dialogue_state
from persona.cognitive_modules.skill_packs.base import BaseSkillPack


class SeekAndChatSkillPack(BaseSkillPack):
    """Find a specific persona first, then hand off to the normal chat skill."""

    def __init__(self):
        super().__init__()
        self.name = "seek_and_chat"
        self.associated_xp = ""

    def can_execute(self, persona, target, maze) -> bool:
        if not str(target or "").strip():
            return self.set_precheck_result(False, "missing_chat_target", {"target": target})
        if str(target).strip() == getattr(persona, "name", None):
            return self.set_precheck_result(False, "self_chat_target", {"target": target})
        return self.set_precheck_result(True, "seek_and_chat_allowed", {"target": target})

    def get_target_tiles(self, persona, target, maze) -> list:
        return [persona.scratch.curr_tile]

    def on_arrive(self, persona, target, maze, personas):
        self.mark_arrival_phase(persona, target=target)
        target_persona = (personas or {}).get(str(target or "").strip())
        if not target_persona:
            self.finish_failure(persona, "seek_chat_target_missing", {"target": target})
            return

        dialogue_id = build_dialogue_id(persona, target_persona)
        objective = self._build_conversation_objective(persona, target_persona.name)
        self.mark_finalizing_phase(persona, metadata={"target": target_persona.name, "result": "handoff_to_chat"})
        self.finish_success(persona)
        set_social_dialogue_state(
            persona,
            dialogue_id,
            partner_name=target_persona.name,
            role="init",
            topic=objective,
        )
        if getattr(persona.scratch, "begin_complex_skill", None):
            persona.scratch.begin_complex_skill(
                "chat",
                skill_id=dialogue_id,
                phase="pathing",
                owner="init",
                target=target_persona.name,
                metadata={"dialogue_id": dialogue_id, "handoff_from": "seek_and_chat", "topic": objective},
            )
        persona.scratch.add_new_action(
            f"<persona> {target_persona.name}",
            10,
            f"having a conversation with {target_persona.name}",
            "💬",
            (persona.name, "chat with", target_persona.name),
            {"skill_id": "chat with", "target": target_persona.name, "source": "seek_and_chat_handoff", "raw_action": "chat with"},
        )
        log_social_dialogue(
            persona,
            "schedule",
            "seek_and_chat_handoff_to_chat",
            target_name=target_persona.name,
            dialogue_id=dialogue_id,
            payload={"source_skill": "seek_and_chat", "topic": objective},
        )

    def _build_conversation_objective(self, persona, target_name):
        detail = str((getattr(persona.scratch, "act_command", {}) or {}).get("detail") or getattr(persona.scratch, "act_description", "") or "").strip()
        if not detail:
            return f"Find {target_name} and have a purposeful conversation."
        normalized_target = str(target_name or "").strip()
        lowered = detail.lower()
        generic_markers = (
            "having a conversation with",
            "chatting with",
            "talking with",
            "socializing with",
        )
        if any(marker in lowered for marker in generic_markers):
            return f"Find {normalized_target} and discuss the reason you deliberately sought them out."
        return detail
