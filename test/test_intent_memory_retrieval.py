import datetime
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


if "openai" not in sys.modules:
    openai_stub = SimpleNamespace(
        api_key=None,
        api_base=None,
        ChatCompletion=SimpleNamespace(create=lambda **kwargs: {"choices": [{"message": {"content": "stub"}}]}),
        Embedding=SimpleNamespace(create=lambda **kwargs: {"data": [{"embedding": [1.0, 0.0]}]}),
    )
    sys.modules["openai"] = openai_stub

if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda a: sum(x * x for x in a) ** 0.5
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub


from persona.memory_structures.associative_memory import AssociativeMemory
import persona.cognitive_modules.intent_memory as intent_memory
import persona.cognitive_modules.retrieve as retrieve_module
from test.check_seed_experience_memories import ensure_associative_memory_dir, seed_associative_memory


def fake_embedding(text):
    lowered = str(text or "").lower()
    if any(keyword in lowered for keyword in ["food", "eat", "consume", "refrigerator", "apple", "meal", "satiety", "hunger"]):
        return [1.0, 0.0]
    if any(keyword in lowered for keyword in ["rest", "sleep", "bed", "sofa", "stamina"]):
        return [0.0, 1.0]
    if any(keyword in lowered for keyword in ["health", "heal", "healing", "treatment", "injury", "medicine"]):
        return [0.6, 0.8]
    if any(keyword in lowered for keyword in ["mood", "happy", "comfort", "relax", "music", "joy"]):
        return [0.4, 0.9]
    return [0.2, 0.8]


def make_persona_with_memory(memory_dir):
    a_mem = AssociativeMemory(str(memory_dir))
    scratch = SimpleNamespace(
        curr_time=datetime.datetime(2026, 7, 2, 9, 0, 0),
        curr_step=12,
        satiety=18.0,
        stamina=72.0,
        health=85.0,
        mood=68.0,
        recency_w=1.0,
        relevance_w=1.0,
        importance_w=1.0,
        recency_decay=0.99,
        recent_completed_action_signature=None,
        get_str_firstname=lambda: "Maria",
    )
    return SimpleNamespace(name="Maria Lopez", a_mem=a_mem, scratch=scratch)


class IntentMemoryRetrievalTests(unittest.TestCase):
    def test_seeded_food_experience_is_written_and_ranked_first(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = Path(tmpdir)
            ensure_associative_memory_dir(memory_dir)
            persona = make_persona_with_memory(memory_dir)
            seed_associative_memory(
                persona.a_mem,
                persona.name,
                [
                    {
                        "type": "thought",
                        "description": "Maria Lopez gathered apples from the refrigerator and restored her satiety effectively.",
                        "s": "Maria Lopez",
                        "p": "restored satiety via",
                        "o": "refrigerator",
                        "keywords": {"refrigerator", "apple", "food", "satiety", "gather"},
                        "poignancy": 9.0,
                        "attribute_effects": {"satiety": 20.0, "stamina": 0.0, "health": 0.0, "mood": 2.0},
                    },
                    {
                        "type": "event",
                        "description": "Maria Lopez consumed a cooked meal and recovered from hunger quickly.",
                        "s": "Maria Lopez",
                        "p": "consumed",
                        "o": "cooked meal",
                        "keywords": {"consume", "food", "meal", "hunger", "satiety"},
                        "poignancy": 8.0,
                        "attribute_effects": {"satiety": 40.0, "stamina": 0.0, "health": 5.0, "mood": 10.0},
                    },
                    {
                        "type": "thought",
                        "description": "Maria Lopez had a pleasant chat with Klaus Mueller in the plaza.",
                        "s": "Maria Lopez",
                        "p": "chatted with",
                        "o": "Klaus Mueller",
                        "keywords": {"chat", "social", "plaza", "klaus mueller"},
                        "poignancy": 8.0,
                        "attribute_effects": {"satiety": 0.0, "stamina": 0.0, "health": 0.0, "mood": 3.0},
                    },
                ],
                created=persona.scratch.curr_time,
                embedding_fn=fake_embedding,
            )
            persona.a_mem.save(str(memory_dir))
            reloaded = AssociativeMemory(str(memory_dir))
            persona.a_mem = reloaded

            with patch.object(retrieve_module, "get_embedding", side_effect=fake_embedding), \
                 patch.object(intent_memory, "append_debug_log") as log_mock:
                retrieved_nodes = intent_memory.retrieve_intent_memories(
                    persona,
                    intent_family="restore_satiety",
                    action_signature={"intent_family": "restore_satiety"},
                    n_count=3,
                )

            self.assertEqual(len(reloaded.id_to_node), 3)
            top_descriptions = [node.description.lower() for node in retrieved_nodes[:2]]
            self.assertTrue(any("refrigerator" in desc or "meal" in desc for desc in top_descriptions))

            payload = log_mock.call_args.args[1]
            self.assertEqual(payload["intent_family"], "restore_satiety")
            self.assertTrue(any("refrigerator" in desc.lower() for desc in payload["selected_memory_descriptions"]))
            self.assertEqual(reloaded.id_to_node["node_1"].attribute_effects["satiety"], 20.0)

    def test_infer_memory_focus_prefers_satiety_crisis(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                satiety=22.0,
                stamina=25.0,
                health=90.0,
                mood=90.0,
                recent_completed_action_signature=None,
            )
        )
        result = intent_memory.infer_memory_focus(persona, action_signature={})
        self.assertEqual(result, "restore_satiety")

    def test_high_satiety_low_mood_prefers_restore_mood(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                satiety=82.0,
                stamina=76.0,
                health=88.0,
                mood=50.0,
                recent_completed_action_signature=None,
            )
        )
        result = intent_memory.infer_memory_focus(persona, action_signature={})
        self.assertEqual(result, "restore_mood")

    def test_low_health_prefers_positive_health_memories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = Path(tmpdir)
            ensure_associative_memory_dir(memory_dir)
            persona = make_persona_with_memory(memory_dir)
            persona.scratch.satiety = 88.0
            persona.scratch.stamina = 82.0
            persona.scratch.health = 35.0
            persona.scratch.mood = 75.0
            seed_associative_memory(
                persona.a_mem,
                persona.name,
                [
                    {
                        "type": "event",
                        "description": "Maria Lopez rested carefully and recovered her health after treatment.",
                        "s": "Maria Lopez",
                        "p": "recovered",
                        "o": "health",
                        "keywords": {"health", "recover", "treatment", "rest"},
                        "poignancy": 8.0,
                        "attribute_effects": {"satiety": 0.0, "stamina": 5.0, "health": 18.0, "mood": 0.0},
                    },
                    {
                        "type": "event",
                        "description": "Maria Lopez kept working through pain and felt worse physically.",
                        "s": "Maria Lopez",
                        "p": "strained",
                        "o": "health",
                        "keywords": {"health", "pain", "work"},
                        "poignancy": 8.0,
                        "attribute_effects": {"satiety": 0.0, "stamina": -5.0, "health": -12.0, "mood": -2.0},
                    },
                ],
                created=persona.scratch.curr_time,
                embedding_fn=fake_embedding,
            )
            persona.a_mem.save(str(memory_dir))
            persona.a_mem = AssociativeMemory(str(memory_dir))

            with patch.object(retrieve_module, "get_embedding", side_effect=fake_embedding):
                retrieved_nodes = intent_memory.retrieve_intent_memories(
                    persona,
                    intent_family="restore_health",
                    action_signature={"intent_family": "restore_health"},
                    n_count=2,
                )

            self.assertEqual(retrieved_nodes[0].attribute_effects["health"], 18.0)
            self.assertIn("recovered her health", retrieved_nodes[0].description.lower())

    def test_idle_only_memories_do_not_crash_intent_retrieval(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = Path(tmpdir)
            ensure_associative_memory_dir(memory_dir)
            persona = make_persona_with_memory(memory_dir)
            seed_associative_memory(
                persona.a_mem,
                persona.name,
                [
                    {
                        "type": "event",
                        "description": "Maria Lopez was idle near the dorm entrance.",
                        "s": "Maria Lopez",
                        "p": "was",
                        "o": "idle",
                        "keywords": {"idle", "dorm"},
                        "poignancy": 1.0,
                    },
                ],
                created=persona.scratch.curr_time,
                embedding_fn=lambda text: [0.1, 0.1],
            )
            persona.a_mem.save(str(memory_dir))
            persona.a_mem = AssociativeMemory(str(memory_dir))

            with patch.object(retrieve_module, "get_embedding", return_value=[0.1, 0.1]):
                retrieved_nodes = intent_memory.retrieve_intent_memories(
                    persona,
                    intent_family="restore_satiety",
                    action_signature={"intent_family": "restore_satiety"},
                    n_count=3,
                )

            self.assertEqual(retrieved_nodes, [])


if __name__ == "__main__":
    unittest.main()
