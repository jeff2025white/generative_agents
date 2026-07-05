import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sys.modules.setdefault("openai", SimpleNamespace(api_key=None, api_base=None))
if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.dot = lambda *args, **kwargs: 0.0
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda *args, **kwargs: 1.0
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub

from persona.memory_structures.scratch import Scratch


class ScratchLegacyLoadTests(unittest.TestCase):
    def _build_legacy_payload(self):
        return {
            "vision_r": 4,
            "att_bandwidth": 3,
            "retention": 5,
            "curr_time": "July 02, 2026, 17:09:29",
            "curr_tile": [10, 12],
            "daily_plan_req": "stay healthy",
            "name": "Klaus Mueller",
            "first_name": "Klaus",
            "last_name": "Mueller",
            "age": 28,
            "innate": "kind",
            "learned": "likes reading",
            "currently": "testing compatibility",
            "lifestyle": "regular",
            "living_area": "Dorm",
            "satiety": 55.0,
            "stamina": 80.0,
            "health": 90.0,
            "mood": 75.0,
            "concept_forget": 100,
            "daily_reflection_time": 180,
            "daily_reflection_size": 5,
            "overlap_reflect_th": 2,
            "kw_strg_event_reflect_th": 4,
            "kw_strg_thought_reflect_th": 4,
            "recency_w": 1,
            "relevance_w": 1,
            "importance_w": 1,
            "recency_decay": 0.99,
            "importance_trigger_max": 150,
            "importance_trigger_curr": 150,
            "importance_ele_n": 0,
            "thought_count": 5,
            "daily_req": [],
            "f_daily_schedule": [],
            "f_daily_schedule_hourly_org": [],
            "act_address": None,
            "act_start_time": None,
            "act_duration": None,
            "act_description": None,
            "act_pronunciatio": None,
            "act_event": None,
            "act_obj_description": None,
            "act_obj_pronunciatio": None,
            "act_obj_event": None,
            "act_path_set": False,
            "planned_path": [],
        }

    def test_load_legacy_scratch_with_none_act_event(self):
        payload = self._build_legacy_payload()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp)
            temp_path = tmp.name

        try:
            scratch = Scratch(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

        self.assertEqual(scratch.act_event, ("Klaus Mueller", None, None))
        self.assertEqual(scratch.act_obj_event, (None, None, None))

    def test_load_legacy_empty_act_address_normalizes_to_none(self):
        payload = self._build_legacy_payload()
        payload["act_address"] = "   "
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp)
            temp_path = tmp.name

        try:
            scratch = Scratch(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

        self.assertIsNone(scratch.act_address)

    def test_resume_suspended_action_normalizes_empty_address(self):
        scratch = Scratch(str(ROOT / "test" / "__missing_scratch__.json"))
        scratch.suspended_action = {
            "act_address": " ",
            "act_duration": 10,
            "act_description": "having a conversation with Maria Lopez",
            "act_pronunciatio": "💬",
            "act_event": ["Klaus Mueller", "chat with", "Maria Lopez"],
            "act_command": {"skill_id": "chat with", "target": "Maria Lopez"},
            "act_obj_description": None,
            "act_obj_pronunciatio": None,
            "act_obj_event": [None, None, None],
            "chatting_with": "Maria Lopez",
            "chat": None,
            "chatting_with_buffer": {},
            "chatting_end_time": None,
        }

        self.assertTrue(scratch.resume_suspended_action())
        self.assertIsNone(scratch.act_address)

    def test_missing_file_uses_lower_default_mood(self):
        scratch = Scratch(str(ROOT / "test" / "__missing_scratch__.json"))
        self.assertEqual(scratch.mood, 50.0)


if __name__ == "__main__":
    unittest.main()
