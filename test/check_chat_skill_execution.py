"""Exercise the real execute -> skill registry -> ChatSkillPack path.

This script avoids network dependence by patching the chat LLM calls to return
deterministic test data, while still routing through the same execution entry
point used by the simulation.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from persona.cognitive_modules.action_command_utils import build_action_command
from persona.cognitive_modules.execute import execute
from persona.cognitive_modules.skill_packs import SKILL_REGISTRY
from persona.cognitive_modules.skill_packs.chat_skill import ChatSkillPack
from persona.cognitive_modules.social_dialogue_log import set_social_dialogue_state
from persona.memory_structures.scratch import Scratch


class FakeMemory:
    def __init__(self):
        self.relationships = {}
        self.events = []
        self._node_index = 0

    def get_relationship(self, name):
        return self.relationships.get(name)

    def update_relationship(self, name, relation_type=None, trust_delta=0.0, trust_absolute=None, recent_event=None):
        rel = dict(self.relationships.get(name) or {"relationship": "acquaintance", "trust": 0.5, "recent_events": []})
        if relation_type:
            rel["relationship"] = relation_type
        if trust_absolute is not None:
            rel["trust"] = float(trust_absolute)
        else:
            rel["trust"] = max(0.0, min(1.0, float(rel.get("trust", 0.0)) + float(trust_delta or 0.0)))
        if recent_event:
            rel.setdefault("recent_events", []).append(recent_event)
        self.relationships[name] = rel

    def add_event(self, *args, **kwargs):
        self._node_index += 1
        node = SimpleNamespace(node_id=f"node_{self._node_index}", args=args, kwargs=kwargs)
        self.events.append(node)
        return node


class FakeMaze:
    collision_maze = [[0]]

    def get_tile_path(self, tile, level):
        _ = tile
        _ = level
        return "test_arena"

    def access_tile(self, tile):
        _ = tile
        return {"collision": False, "game_object": "test bench"}


class FakePersona:
    def __init__(self, name, tile):
        self.name = name
        self.sim_code = "script_chat_skill_check"
        self.a_mem = FakeMemory()
        self.s_mem = SimpleNamespace(find_nearest_object=lambda _target: None)
        self.scratch = Scratch("__missing_chat_skill_check__.json")
        self.scratch.name = name
        self.scratch.first_name = name.split()[0]
        self.scratch.last_name = name.split()[-1]
        self.scratch.curr_time = dt.datetime(2026, 7, 7, 14, 0, 0)
        self.scratch.curr_step = 1
        self.scratch.curr_tile = list(tile)
        self.scratch.chatting_with_buffer = {}
        self.scratch.skills.setdefault("cooking", {"level": 1, "xp": 0})
        self.scratch.skills.setdefault("gathering", {"level": 1, "xp": 0})
        self.scratch.skills.setdefault("singing", {"level": 1, "xp": 0})


def prime_chat_action(initiator, target):
    initiator.scratch.add_new_action(
        f"<persona> {target.name}",
        10,
        f"having a conversation with {target.name}",
        "💬",
        (initiator.name, "chat with", target.name),
        build_action_command("chat with", target.name, source="script_check", raw_action="chat with"),
        target.name,
        None,
        {},
        initiator.scratch.curr_time + dt.timedelta(minutes=10),
        None,
        None,
        (None, None, None),
        initiator.scratch.curr_time,
    )
    initiator.scratch.act_path_set = True
    initiator.scratch.planned_path = []
    initiator.scratch.survival_applied = False
    set_social_dialogue_state(initiator, "dlg_script_chat_check", partner_name=target.name, role="init")


def main():
    registry_skill = SKILL_REGISTRY.get("chat with")
    assert isinstance(registry_skill, ChatSkillPack), "Registry is not wired to ChatSkillPack for 'chat with'"

    initiator = FakePersona("Klaus Mueller", (0, 0))
    target = FakePersona("Maria Lopez", (0, 0))
    personas = {
        initiator.name: initiator,
        target.name: target,
    }
    prime_chat_action(initiator, target)

    fixed_convo = [
        [initiator.name, "你好，玛丽亚，今天过得怎么样？"],
        [target.name, "还不错，我刚在附近转了一圈。"],
        [initiator.name, "那挺好，等会儿一起去喝杯咖啡吧。"],
        [target.name, "好啊，听起来不错。"],
    ]
    transcript_records = []
    social_records = []

    with patch.object(
        ChatSkillPack,
        "cognitive_decision",
        return_value={
            "mode": "social",
            "convo": fixed_convo,
            "target_persona_name": target.name,
        },
    ), patch(
        "persona.cognitive_modules.skill_packs.chat_skill.get_embedding",
        return_value=[0.0],
    ), patch(
        "persona.prompt_template.run_gpt_prompt.run_gpt_prompt_summarize_conversation",
        return_value=("conversing about having coffee together", None),
    ), patch(
        "persona.prompt_template.gpt_structure.ChatGPT_single_request",
        return_value="none",
    ), patch(
        "persona.cognitive_modules.skill_packs.chat_skill.log_chat_transcript",
        side_effect=lambda *args, **kwargs: transcript_records.append((args, kwargs)),
    ), patch(
        "persona.cognitive_modules.skill_packs.chat_skill.log_social_dialogue",
        side_effect=lambda *args, **kwargs: social_records.append((args, kwargs)),
    ):
        result = execute(initiator, FakeMaze(), personas, initiator.scratch.act_address)

    print("registry_skill_class:", registry_skill.__class__.__name__)
    print("execute_result:", result)
    print("transcript_records:", len(transcript_records))
    print("social_records:", len(social_records))
    print("initiator_last_chat:", initiator.scratch.last_chat)
    print("target_last_chat:", target.scratch.last_chat)
    print("initiator_memory_events:", len(initiator.a_mem.events))
    print("target_memory_events:", len(target.a_mem.events))
    print("initiator_recent_completed:", initiator.scratch.recent_completed_action_signature)
    print("initiator_active_skill_status:", initiator.scratch.active_skill_status)

    assert transcript_records, "ChatSkillPack never wrote a transcript"
    assert social_records, "ChatSkillPack never emitted social dialogue events"
    assert initiator.scratch.last_chat == fixed_convo[-2][1], "Initiator last_chat not updated from conversation"
    assert target.scratch.last_chat == fixed_convo[-1][1], "Target last_chat not updated from conversation"
    assert initiator.a_mem.events, "Initiator memory settlement did not happen"
    assert initiator.scratch.recent_completed_action_signature, "Action completion was not recorded"
    assert initiator.scratch.active_skill_status is None, "Complex skill state was not released"

    print("CHAT_SKILL_EXECUTED=1")


if __name__ == "__main__":
    main()
