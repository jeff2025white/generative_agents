import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from persona.memory_structures.scratch import Scratch


class ChatStorageContractTests(unittest.TestCase):
    """Contract tests for chat persistence boundaries."""

    def test_scratch_save_omits_persisted_chat_fields(self):
        scratch = Scratch(str(ROOT / "test" / "__missing_scratch_contract__.json"))
        scratch.curr_time = datetime(2026, 7, 2, 16, 0, 0)
        scratch.curr_tile = [10, 12]
        scratch.daily_plan_req = "stay productive"
        scratch.name = "Klaus Mueller"
        scratch.first_name = "Klaus"
        scratch.last_name = "Mueller"
        scratch.age = 20
        scratch.innate = "curious"
        scratch.learned = "thoughtful"
        scratch.currently = "chatting"
        scratch.lifestyle = "student"
        scratch.living_area = "dorm"
        scratch.act_address = "<persona> Maria Lopez"
        scratch.act_start_time = datetime(2026, 7, 2, 16, 0, 0)
        scratch.act_duration = 10
        scratch.act_description = "having a conversation with Maria Lopez"
        scratch.act_pronunciatio = "💬"
        scratch.act_event = ("Klaus Mueller", "chat with", "Maria Lopez")
        scratch.act_command = {"skill_id": "chat", "target": "Maria Lopez"}
        scratch.act_obj_description = None
        scratch.act_obj_pronunciatio = None
        scratch.act_obj_event = (None, None, None)
        scratch.chatting_with = "Maria Lopez"
        scratch.chat = [["Maria Lopez", "Hi Klaus!"], ["Klaus Mueller", "Hi Maria."]]
        scratch.last_chat = "Hi Maria."
        scratch.chatting_with_buffer = {"Maria Lopez": 12}
        scratch.chatting_end_time = datetime(2026, 7, 2, 16, 10, 0)
        scratch.social_dialogue_id = "dlg_Klaus_Mueller_Maria_Lopez_20260702_160000_0"
        scratch.social_dialogue_partner = "Maria Lopez"
        scratch.social_dialogue_role = "init"
        scratch.social_dialogue_started_step = 0
        scratch.act_path_set = False
        scratch.planned_path = []

        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "scratch.json"
            scratch.save(str(out_path))
            saved = json.loads(out_path.read_text(encoding="utf-8"))

        self.assertNotIn("chatting_with", saved)
        self.assertNotIn("chat", saved)
        self.assertNotIn("last_chat", saved)
        self.assertNotIn("chatting_with_buffer", saved)
        self.assertNotIn("chatting_end_time", saved)
        self.assertNotIn("social_dialogue_id", saved)
        self.assertNotIn("social_dialogue_partner", saved)
        self.assertNotIn("social_dialogue_role", saved)
        self.assertNotIn("social_dialogue_started_step", saved)


if __name__ == "__main__":
    unittest.main()
