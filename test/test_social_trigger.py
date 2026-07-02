import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from persona.cognitive_modules.social_trigger import (
    choose_social_focus,
    compute_social_cooldown,
    compute_social_opportunity_score,
    should_auto_initiate_social_chat,
    should_run_periodic_social_scan,
)


class FakeMemory:
    """Minimal relationship store for social trigger tests."""

    def __init__(self, relationships=None):
        self.relationships = relationships or {}

    def get_relationship(self, name):
        return self.relationships.get(name)


class FakeNode:
    """Minimal concept node used by retrieved-memory fixtures."""

    def __init__(self, subject, description):
        self.subject = subject
        self.description = description
        self.embedding_key = description


def make_persona(name, tile=(0, 0), act_description="reading quietly", act_address="the Ville:library:desk", buffer=None, relationships=None, mood=70.0, stamina=80.0, satiety=80.0, curr_step=10):
    """Create a SimpleNamespace persona fixture."""
    scratch = SimpleNamespace(
        act_address=act_address,
        act_description=act_description,
        chatting_with=None,
        chatting_with_buffer=buffer or {},
        curr_time=datetime(2026, 7, 1, 14, 0, 0),
        curr_tile=tile,
        mood=mood,
        stamina=stamina,
        satiety=satiety,
        curr_step=curr_step,
        planned_path=[(1, 0), (2, 0)],
        act_event=(name, "work", "desk"),
        last_social_time=datetime(2026, 7, 1, 10, 0, 0),
        should_defer_social_interrupts=lambda: False,
    )
    return SimpleNamespace(name=name, scratch=scratch, a_mem=FakeMemory(relationships))


class SocialTriggerTests(unittest.TestCase):
    def test_opportunity_score_remains_positive_with_soft_cooldown_penalty(self):
        initiator = make_persona(
            "Klaus Mueller",
            tile=(1, 1),
            buffer={"Maria Lopez": 80},
            relationships={"Maria Lopez": {"relationship": "friend", "trust": 0.9}},
        )
        target = make_persona(
            "Maria Lopez",
            tile=(2, 1),
            act_description="waiting for coffee",
            act_address="<waiting> 2 1",
        )
        retrieved = {
            "curr_event": FakeNode("Maria Lopez", "Maria Lopez is waiting for coffee"),
            "events": [FakeNode("Maria Lopez", "Maria Lopez heard fresh town gossip")],
            "thoughts": [FakeNode("Maria Lopez", "Klaus wants to check on Maria Lopez")],
        }

        score = compute_social_opportunity_score(initiator, target, retrieved)

        self.assertGreaterEqual(score["total"], 0.24)
        self.assertGreater(score["state_score"], 0.0)
        self.assertGreater(score["recent_chat_penalty"], 0.0)

    def test_dynamic_cooldown_shrinks_for_high_affinity_interactions(self):
        initiator = make_persona(
            "Klaus Mueller",
            relationships={"Maria Lopez": {"relationship": "friend", "trust": 1.0}},
        )
        target = make_persona("Maria Lopez", act_description="waiting near the counter", act_address="<waiting> 2 1")
        retrieved = {
            "curr_event": FakeNode("Maria Lopez", "Maria Lopez is nearby"),
            "events": [FakeNode("Maria Lopez", "Maria Lopez has fresh news")],
            "thoughts": [],
        }

        score = compute_social_opportunity_score(initiator, target, retrieved)
        cooldown = compute_social_cooldown(initiator, target, retrieved, score)

        self.assertGreaterEqual(cooldown, 40)
        self.assertLessEqual(cooldown, 220)
        self.assertLess(cooldown, 120)

    def test_choose_social_focus_prefers_higher_scoring_persona(self):
        initiator = make_persona(
            "Klaus Mueller",
            tile=(1, 1),
            relationships={"Maria Lopez": {"relationship": "friend", "trust": 0.8}},
        )
        maria = make_persona("Maria Lopez", tile=(2, 1), act_description="waiting outside the cafe", act_address="<waiting> 2 1")
        isabella = make_persona("Isabella Rodriguez", tile=(8, 8), act_description="working at the counter")
        personas = {
            "Klaus Mueller": initiator,
            "Maria Lopez": maria,
            "Isabella Rodriguez": isabella,
        }
        retrieved = {
            "maria_event": {
                "curr_event": FakeNode("Maria Lopez", "Maria Lopez is waiting outside the cafe"),
                "events": [FakeNode("Maria Lopez", "Maria Lopez heard a new rumor")],
                "thoughts": [],
            },
            "isabella_event": {
                "curr_event": FakeNode("Isabella Rodriguez", "Isabella Rodriguez is working at the counter"),
                "events": [],
                "thoughts": [],
            },
        }

        focus, candidates = choose_social_focus(initiator, retrieved, personas)

        self.assertEqual(focus["curr_event"].subject, "Maria Lopez")
        self.assertEqual(len(candidates), 2)

    def test_periodic_social_scan_only_runs_on_interval(self):
        initiator = make_persona("Klaus Mueller", curr_step=10)
        self.assertTrue(should_run_periodic_social_scan(initiator, interval=5))
        initiator.scratch.curr_step = 11
        self.assertFalse(should_run_periodic_social_scan(initiator, interval=5))

    def test_periodic_social_scan_skips_committed_survival_route(self):
        initiator = make_persona("Klaus Mueller", curr_step=10, act_description="walking to the refrigerator")
        initiator.scratch.act_event = ("Klaus Mueller", "gather", "refrigerator")
        initiator.scratch.should_defer_social_interrupts = lambda: True

        self.assertFalse(should_run_periodic_social_scan(initiator, interval=5))

    def test_social_score_includes_switch_cost_penalty_when_commitment_active(self):
        initiator = make_persona("Klaus Mueller", act_description="working quietly at the desk")
        initiator.scratch.compute_switch_cost = lambda action_signature: 0.18
        initiator.scratch.is_recent_duplicate_action = lambda action_signature, within_steps=6: False
        initiator.scratch.decision_commit_until_step = 20
        initiator.scratch.curr_step = 11
        target = make_persona(
            "Maria Lopez",
            tile=(2, 1),
            act_description="waiting for coffee",
            act_address="<waiting> 2 1",
        )
        retrieved = {
            "curr_event": FakeNode("Maria Lopez", "Maria Lopez is waiting for coffee"),
            "events": [],
            "thoughts": [],
        }

        score = compute_social_opportunity_score(initiator, target, retrieved)

        self.assertGreater(score["switch_cost_penalty"], 0.0)
        self.assertIn("recent_duplicate_penalty", score)

    def test_high_opportunity_score_can_auto_initiate(self):
        score_detail = {
            "total": 0.51,
            "urgency_penalty": 0.0,
            "novelty_bonus": 0.16,
            "state_score": 0.04,
            "social_need_bonus": 0.08,
        }
        self.assertTrue(should_auto_initiate_social_chat(score_detail))


if __name__ == "__main__":
    unittest.main()
