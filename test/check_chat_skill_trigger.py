"""Verify that social scanning can auto-trigger and execute the chat skill."""

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


from persona.cognitive_modules.execute import execute
from persona.cognitive_modules.plan import plan_social_reaction
from persona.cognitive_modules.skill_packs.chat_skill import ChatSkillPack
from persona.memory_structures.scratch import Scratch


class FakeMemory:
    def __init__(self, default_relationship=None):
        self.relationships = {}
        self.events = []
        self._node_index = 0
        self.default_relationship = default_relationship or {
            "relationship": "friend",
            "trust": 0.82,
            "recent_events": ["shared coffee recently", "talked about town gossip"],
        }

    def get_relationship(self, name):
        return self.relationships.get(name, dict(self.default_relationship))

    def update_relationship(self, name, relation_type=None, trust_delta=0.0, trust_absolute=None, recent_event=None):
        rel = dict(self.get_relationship(name))
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
    collision_maze = [
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
    ]

    def get_tile_path(self, tile, level):
        _ = tile
        _ = level
        return "town square"

    def access_tile(self, tile):
        _ = tile
        return {"collision": False, "game_object": "plaza bench", "events": set()}


class FakePersona:
    def __init__(self, name, tile):
        self.name = name
        self.sim_code = "script_chat_trigger_check"
        self.a_mem = FakeMemory()
        self.s_mem = SimpleNamespace(find_nearest_object=lambda _target: None)
        self.scratch = Scratch("__missing_chat_trigger_check__.json")
        self.scratch.name = name
        self.scratch.first_name = name.split()[0]
        self.scratch.last_name = name.split()[-1]
        self.scratch.curr_time = dt.datetime(2026, 7, 7, 14, 10, 0)
        self.scratch.curr_step = 10
        self.scratch.curr_tile = list(tile)
        self.scratch.act_address = "the Ville:Town Square:plaza bench"
        self.scratch.act_description = "idling near the plaza bench"
        self.scratch.act_event = (name, "idle", "plaza bench")
        self.scratch.chatting_with_buffer = {}
        self.scratch.last_social_time = None
        self.scratch.mood = 52.0
        self.scratch.stamina = 88.0
        self.scratch.satiety = 82.0
        self.scratch.planned_path = [(0, 0)]
        self.scratch.skills.setdefault("cooking", {"level": 1, "xp": 0})
        self.scratch.skills.setdefault("gathering", {"level": 1, "xp": 0})
        self.scratch.skills.setdefault("singing", {"level": 1, "xp": 0})


def build_retrieved(target_name):
    node = SimpleNamespace(
        subject=target_name,
        description=f"{target_name} is idling in the square and seems available to talk.",
        embedding_key=f"{target_name} is idling in the square and seems available to talk.",
    )
    return {
        "nearby_target": {
            "curr_event": node,
            "events": [node],
            "thoughts": [],
        }
    }


def main():
    initiator = FakePersona("Klaus Mueller", (0, 0))
    target = FakePersona("Maria Lopez", (1, 0))
    personas = {
        initiator.name: initiator,
        target.name: target,
    }
    retrieved = build_retrieved(target.name)
    social_records = []
    transcript_records = []

    fixed_convo = [
        [initiator.name, "玛丽亚，今天天气不错。"],
        [target.name, "是啊，广场这边风也挺舒服。"],
        [initiator.name, "等会儿要不要一起走走？"],
        [target.name, "好啊，我正好也有空。"],
    ]

    with patch(
        "persona.cognitive_modules.plan.log_social_dialogue",
        side_effect=lambda *args, **kwargs: social_records.append(("plan", args, kwargs)),
    ), patch(
        "persona.cognitive_modules.skill_packs.chat_skill.log_social_dialogue",
        side_effect=lambda *args, **kwargs: social_records.append(("skill", args, kwargs)),
    ), patch(
        "persona.cognitive_modules.skill_packs.chat_skill.log_chat_transcript",
        side_effect=lambda *args, **kwargs: transcript_records.append((args, kwargs)),
    ), patch(
        "persona.cognitive_modules.skill_packs.chat_skill.get_embedding",
        return_value=[0.0],
    ), patch(
        "persona.prompt_template.run_gpt_prompt.run_gpt_prompt_summarize_conversation",
        return_value=("conversing about taking a walk together", None),
    ), patch(
        "persona.prompt_template.gpt_structure.ChatGPT_single_request",
        return_value="none",
    ), patch.object(
        ChatSkillPack,
        "cognitive_decision",
        return_value={
            "mode": "social",
            "convo": fixed_convo,
            "target_persona_name": target.name,
        },
    ):
        plan_social_reaction(initiator, FakeMaze(), personas, retrieved)

        print("after_scan_act_event:", initiator.scratch.act_event)
        print("after_scan_act_address:", initiator.scratch.act_address)
        print("after_scan_dialogue_id:", initiator.scratch.social_dialogue_id)
        print("after_scan_active_skill:", initiator.scratch.active_skill_name, initiator.scratch.active_skill_phase)

        assert initiator.scratch.act_event[1] == "chat with", "Social scan did not enqueue a chat action"
        assert initiator.scratch.social_dialogue_id, "Dialogue state was not assigned during trigger"
        assert initiator.scratch.active_skill_name == "chat", "Chat complex skill was not started"

        result = execute(initiator, FakeMaze(), personas, initiator.scratch.act_address)

    print("execute_result:", result)
    print("transcript_records:", len(transcript_records))
    print("social_records:", len(social_records))
    print("initiator_recent_completed:", initiator.scratch.recent_completed_action_signature)
    print("initiator_active_skill_status:", initiator.scratch.active_skill_status)
    print("initiator_last_chat:", initiator.scratch.last_chat)
    print("target_last_chat:", target.scratch.last_chat)

    assert transcript_records, "Triggered chat never wrote a transcript"
    assert social_records, "Triggered chat emitted no social records"
    assert initiator.scratch.recent_completed_action_signature, "Triggered chat never completed"
    assert initiator.scratch.active_skill_status is None, "Triggered chat left active skill state uncleared"

    print("CHAT_TRIGGERED_AND_EXECUTED=1")


if __name__ == "__main__":
    main()
