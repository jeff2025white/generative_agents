import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


if "openai" not in sys.modules:
    openai_stub = types.SimpleNamespace(
        api_key=None,
        api_base=None,
        ChatCompletion=types.SimpleNamespace(
            create=lambda **kwargs: {"choices": [{"message": {"content": "stub"}}]}
        ),
        Embedding=types.SimpleNamespace(
            create=lambda **kwargs: {"data": [{"embedding": [1.0, 0.0]}]}
        ),
    )
    sys.modules["openai"] = openai_stub


from persona.cognitive_modules.action_command_utils import normalize_skill_id
from persona.cognitive_modules.skill_packs.give_skill import GiveSkillPack
from persona.cognitive_modules.skill_packs.rob_skill import RobSkillPack


class DummyAssociativeMemory:
    def __init__(self):
        self.social_relationship_graph = {"relations": {}}

    def add_event(self, *args, **kwargs):
        return {"args": args, "kwargs": kwargs}

    def get_relationship(self, target_name):
        return self.social_relationship_graph.get("relations", {}).get(target_name)

    def update_relationship(self, target_name, relation_type=None, trust_delta=0, trust_absolute=None, recent_event=None):
        relations = self.social_relationship_graph.setdefault("relations", {})
        rel = relations.setdefault(
            target_name,
            {"relationship": "stranger", "trust": 0.5, "recent_events": []},
        )
        if relation_type:
            rel["relationship"] = relation_type
        if trust_absolute is not None:
            rel["trust"] = max(0.0, min(1.0, float(trust_absolute)))
        elif trust_delta:
            rel["trust"] = max(0.0, min(1.0, float(rel.get("trust", 0.5)) + float(trust_delta)))
        if recent_event:
            rel.setdefault("recent_events", []).append(recent_event)


class DummyScratch:
    def __init__(self, name, inventory=None, mood=50.0, curr_tile=(0, 0)):
        self.name = name
        self.inventory = dict(inventory or {})
        self.mood = mood
        self.satiety = 50.0
        self.stamina = 50.0
        self.health = 50.0
        self.curr_tile = curr_tile
        self.curr_time = None
        self.act_address = f"<persona> {name}"
        self.act_description = None
        self.act_event = None
        self.act_command = None
        self.planned_path = []
        self.act_path_set = False
        self.first_name = str(name).split()[0]

    def mark_action_completed(self, **kwargs):
        self.last_completed_action = kwargs


class DummyPersona:
    def __init__(self, name, inventory=None, mood=50.0, curr_tile=(0, 0)):
        self.name = name
        self.scratch = DummyScratch(name, inventory=inventory, mood=mood, curr_tile=curr_tile)
        self.a_mem = DummyAssociativeMemory()


class TransferSkillTests(unittest.TestCase):
    def test_action_aliases_map_to_new_transfer_skills(self):
        self.assertEqual(normalize_skill_id("gift", target="Maria Lopez"), "give")
        self.assertEqual(normalize_skill_id("share", target="Klaus Mueller"), "give")
        self.assertEqual(normalize_skill_id("steal", target="Maria Lopez"), "rob")
        self.assertEqual(normalize_skill_id("loot", target="Klaus Mueller"), "rob")

    def test_give_skill_moves_one_item_to_target_inventory(self):
        actor = DummyPersona("Isabella Rodriguez", inventory={"apple": 2}, mood=55.0, curr_tile=(10, 10))
        actor.scratch.act_description = "giving an apple to Maria Lopez"
        actor.scratch.act_event = (actor.name, "give", "Maria Lopez")
        actor.scratch.act_command = {"skill_id": "give", "target": "Maria Lopez", "detail": actor.scratch.act_description}
        target = DummyPersona("Maria Lopez", inventory={}, mood=40.0, curr_tile=(11, 10))

        GiveSkillPack().on_arrive(actor, "Maria Lopez", maze=None, personas=[actor, target])

        self.assertEqual(actor.scratch.inventory["apple"], 1)
        self.assertEqual(target.scratch.inventory["apple"], 1)
        self.assertGreater(actor.scratch.mood, 55.0)
        self.assertGreater(target.scratch.mood, 40.0)
        self.assertEqual(actor.a_mem.get_relationship("Maria Lopez")["relationship"], "friend")
        self.assertGreater(actor.a_mem.get_relationship("Maria Lopez")["trust"], 0.5)
        self.assertEqual(target.a_mem.get_relationship("Isabella Rodriguez")["relationship"], "friend")
        self.assertGreater(target.a_mem.get_relationship("Isabella Rodriguez")["trust"], 0.5)

    def test_rob_skill_moves_one_item_from_target_inventory(self):
        actor = DummyPersona("Klaus Mueller", inventory={}, mood=60.0, curr_tile=(5, 5))
        actor.scratch.act_description = "stealing an apple from Maria Lopez"
        actor.scratch.act_event = (actor.name, "rob", "Maria Lopez")
        actor.scratch.act_command = {"skill_id": "rob", "target": "Maria Lopez", "detail": actor.scratch.act_description}
        target = DummyPersona("Maria Lopez", inventory={"apple": 2}, mood=52.0, curr_tile=(6, 5))

        RobSkillPack().on_arrive(actor, "Maria Lopez", maze=None, personas=[actor, target])

        self.assertEqual(actor.scratch.inventory["apple"], 1)
        self.assertEqual(target.scratch.inventory["apple"], 1)
        self.assertLess(actor.scratch.mood, 60.0)
        self.assertLess(target.scratch.mood, 52.0)
        self.assertEqual(actor.a_mem.get_relationship("Maria Lopez")["relationship"], "enemy")
        self.assertEqual(actor.a_mem.get_relationship("Maria Lopez")["trust"], 0.0)
        self.assertEqual(target.a_mem.get_relationship("Klaus Mueller")["relationship"], "enemy")
        self.assertEqual(target.a_mem.get_relationship("Klaus Mueller")["trust"], 0.0)


if __name__ == "__main__":
    unittest.main()
