import datetime
import json
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
        ChatCompletion=SimpleNamespace(
            create=lambda **kwargs: {"choices": [{"message": {"content": "stub"}}]}
        ),
        Embedding=SimpleNamespace(create=lambda **kwargs: {"data": [{"embedding": [1.0, 0.0]}]}),
    )
    sys.modules["openai"] = openai_stub

if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.array = lambda value, *args, **kwargs: value
    numpy_stub.dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda a: sum(x * x for x in a) ** 0.5
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub


from persona.memory_structures.associative_memory import AssociativeMemory
import reverie as reverie_module
from test.check_seed_experience_memories import ensure_associative_memory_dir, seed_associative_memory


def fake_embedding(text):
    lowered = str(text or "").lower()
    if any(keyword in lowered for keyword in ["food", "eat", "consume", "refrigerator", "apple", "meal", "satiety"]):
        return [1.0, 0.0]
    return [0.3, 0.7]


class AssociativeMemoryDirtyFlagTests(unittest.TestCase):
    def test_associative_memory_marks_dirty_on_new_event_and_clears_on_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = Path(tmpdir)
            ensure_associative_memory_dir(memory_dir)
            a_mem = AssociativeMemory(str(memory_dir))

            self.assertFalse(a_mem.is_dirty())

            seed_associative_memory(
                a_mem,
                "Maria Lopez",
                [
                    {
                        "type": "event",
                        "description": "Maria Lopez consumed an apple and restored satiety.",
                        "s": "Maria Lopez",
                        "p": "consumed",
                        "o": "apple",
                        "keywords": {"food", "consume", "apple", "satiety"},
                        "poignancy": 7.0,
                        "attribute_effects": {"satiety": 40.0, "stamina": 0.0, "health": 5.0, "mood": 10.0},
                    }
                ],
                created=datetime.datetime(2026, 7, 2, 16, 0, 0),
                embedding_fn=fake_embedding,
            )

            self.assertTrue(a_mem.is_dirty())
            a_mem.save(str(memory_dir))
            self.assertFalse(a_mem.is_dirty())


class IncrementalServerPersistenceTests(unittest.TestCase):
    def test_incremental_save_updates_meta_and_only_flushes_dirty_associative_memory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            sim_code = "sim_incremental_test"
            sim_dir = storage_root / sim_code
            (sim_dir / "reverie").mkdir(parents=True, exist_ok=True)
            (sim_dir / "reverie" / "meta.json").write_text(
                json.dumps(
                    {
                        "fork_sim_code": "base_sim",
                        "start_date": "February 13, 2023",
                        "curr_time": "February 13, 2023, 08:00:00",
                        "sec_per_step": 10,
                        "maze_name": "the_ville",
                        "persona_names": ["Dirty Persona", "Clean Persona"],
                        "step": 0,
                    }
                ),
                encoding="utf-8",
            )

            class FakeAssociativeMemory:
                def __init__(self, dirty):
                    self._dirty = dirty

                def is_dirty(self):
                    return self._dirty

            class FakePersona:
                def __init__(self, name, dirty):
                    self.name = name
                    self.a_mem = FakeAssociativeMemory(dirty)
                    self.save_calls = []

                def save(self, save_folder, save_spatial_memory=True, save_associative_memory=True, save_scratch=True):
                    self.save_calls.append(
                        {
                            "save_folder": save_folder,
                            "save_spatial_memory": save_spatial_memory,
                            "save_associative_memory": save_associative_memory,
                            "save_scratch": save_scratch,
                        }
                    )
                    if save_associative_memory:
                        self.a_mem._dirty = False

            dirty_persona = FakePersona("Dirty Persona", dirty=True)
            clean_persona = FakePersona("Clean Persona", dirty=False)

            server = reverie_module.ReverieServer.__new__(reverie_module.ReverieServer)
            server.fork_sim_code = "base_sim"
            server.sim_code = sim_code
            server.start_time = datetime.datetime(2023, 2, 13, 0, 0, 0)
            server.curr_time = datetime.datetime(2023, 2, 13, 8, 5, 0)
            server.sec_per_step = 10
            server.step = 12
            server.maze = SimpleNamespace(maze_name="the_ville")
            server.personas = {
                "Dirty Persona": dirty_persona,
                "Clean Persona": clean_persona,
            }
            server._last_incremental_save_step = 0
            server._last_incremental_save_ts = 0.0

            with patch.object(reverie_module, "fs_storage", str(storage_root)), patch.object(
                reverie_module, "append_debug_log"
            ):
                saved = server.save_incremental_progress()

            self.assertTrue(saved)
            self.assertEqual(len(dirty_persona.save_calls), 1)
            self.assertEqual(len(clean_persona.save_calls), 1)
            self.assertFalse(dirty_persona.save_calls[0]["save_spatial_memory"])
            self.assertTrue(dirty_persona.save_calls[0]["save_associative_memory"])
            self.assertTrue(dirty_persona.save_calls[0]["save_scratch"])
            self.assertFalse(clean_persona.save_calls[0]["save_spatial_memory"])
            self.assertFalse(clean_persona.save_calls[0]["save_associative_memory"])
            self.assertTrue(clean_persona.save_calls[0]["save_scratch"])
            self.assertFalse(dirty_persona.a_mem.is_dirty())

            meta = json.loads((sim_dir / "reverie" / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["step"], 12)
            self.assertEqual(meta["curr_time"], "February 13, 2023, 08:05:00")


if __name__ == "__main__":
    unittest.main()
