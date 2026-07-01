import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(r"g:\generative_agents")
BACKEND = ROOT / "reverie" / "backend_server"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from persona.cognitive_modules import creator_chat_context as ccc


class FakeNode:
    def __init__(self, description):
        self.description = description
        self.embedding_key = description
        self.last_accessed = datetime.now()


class FakeMaze:
    def get_tile_path(self, tile, level):
        mapping = {
            "world": "the Ville",
            "sector": "the Ville:Oak Hill College",
            "arena": "the Ville:Oak Hill College:library",
            "game object": "the Ville:Oak Hill College:library:computer desk",
        }
        return mapping[level]


class CreatorChatContextBuilderTests(unittest.TestCase):
    def test_expected_sections_exist(self):
        original_retrieve = ccc.new_retrieve
        ccc.new_retrieve = lambda persona, focal_points, limit=8: {
            focal_points[0]: [FakeNode("Klaus recently ate an apple")]
        }
        try:
            scratch = SimpleNamespace(
                satiety=61.0,
                stamina=72.0,
                health=91.0,
                mood=66.0,
                act_description="reading at the computer desk",
                act_address="the Ville:Oak Hill College:library:computer desk",
                curr_tile=(1, 1),
                inventory={"apple": 1},
                f_daily_schedule=[("study at the library", 60)],
            )
            a_mem = SimpleNamespace(
                social_relationship_graph={
                    "relations": {
                        "Maria Lopez": {
                            "relationship": "friend",
                            "trust": 0.8,
                            "recent_events": ["studied together"],
                        }
                    }
                }
            )
            persona = SimpleNamespace(name="Klaus Mueller", scratch=scratch, a_mem=a_mem)
            sections = ccc.build_creator_query_context(
                persona,
                FakeMaze(),
                "你现在在做什么？",
                [{"role": "user", "content": "你好"}],
            )
        finally:
            ccc.new_retrieve = original_retrieve

        self.assertEqual(
            sorted(sections.keys()),
            ["environment", "history", "memories", "plans", "relationships", "self_state"],
        )
        self.assertIn("Satiety", sections["self_state"])
        self.assertIn("computer desk", sections["environment"])
        self.assertIn("study at the library", sections["plans"])
        self.assertIn("Klaus recently ate an apple", sections["memories"])
        self.assertIn("Maria Lopez", sections["relationships"])


if __name__ == "__main__":
    unittest.main()
