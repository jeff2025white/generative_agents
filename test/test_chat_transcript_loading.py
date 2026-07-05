import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "environment" / "frontend_server"
BACKEND = ROOT / "reverie" / "backend_server"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "frontend_server.settings")

import django

django.setup()

import translator.views as translator_views


class ChatTranscriptLoadingTests(unittest.TestCase):
    def test_load_chat_transcript_prefers_scoped_run_data(self):
        sim_code = "sim_20260705_144511"
        dialogue_id = "dlg_scoped"
        scoped_record = {
            "sim_code": sim_code,
            "dialogue_id": dialogue_id,
            "persona": "Klaus Mueller",
            "target": "Maria Lopez",
            "sim_time": "2026-07-05 08:23:30",
            "step": 143,
            "ts": "2026-07-05T14:48:10+08:00",
            "conversation": [
                {"speaker": "Klaus Mueller", "utterance": "scoped hello"},
                {"speaker": "Maria Lopez", "utterance": "scoped reply"},
            ],
        }
        global_record = {
            "sim_code": "sim_20260705_145203",
            "dialogue_id": "dlg_other_run",
            "persona": "Klaus Mueller",
            "target": "Maria Lopez",
            "sim_time": "2026-07-05 08:23:30",
            "step": 141,
            "ts": "2026-07-05T14:55:35+08:00",
            "conversation": [
                {"speaker": "Klaus Mueller", "utterance": "global hello"},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            scoped_path = project_root / "environment" / "frontend_server" / "storage" / sim_code / "chat_transcript.jsonl"
            scoped_path.parent.mkdir(parents=True, exist_ok=True)
            scoped_path.write_text(json.dumps(scoped_record, ensure_ascii=False) + "\n", encoding="utf-8")

            logs_path = project_root / "logs" / "chat_transcript.jsonl"
            logs_path.parent.mkdir(parents=True, exist_ok=True)
            logs_path.write_text(json.dumps(global_record, ensure_ascii=False) + "\n", encoding="utf-8")

            with patch.object(translator_views, "_project_root", str(project_root)), \
                 patch.object(translator_views, "_get_sim_log_start_time", return_value=None):
                records = translator_views._load_chat_transcript_records(sim_code, step=143, limit=12)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["dialogue_id"], dialogue_id)
        self.assertEqual(records[0]["conversation"][0]["utterance"], "scoped hello")

    def test_load_chat_transcript_filters_global_records_by_sim_code(self):
        sim_code = "sim_20260705_145203"
        matching_record = {
            "sim_code": sim_code,
            "dialogue_id": "dlg_match",
            "persona": "Klaus Mueller",
            "target": "Maria Lopez",
            "sim_time": "2026-07-05 08:23:30",
            "step": 141,
            "ts": "2026-07-05T14:55:35+08:00",
            "conversation": [
                {"speaker": "Klaus Mueller", "utterance": "match hello"},
            ],
        }
        other_record = {
            "sim_code": "sim_20260705_144511",
            "dialogue_id": "dlg_other",
            "persona": "Klaus Mueller",
            "target": "Maria Lopez",
            "sim_time": "2026-07-05 08:23:30",
            "step": 143,
            "ts": "2026-07-05T14:48:10+08:00",
            "conversation": [
                {"speaker": "Klaus Mueller", "utterance": "other hello"},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            logs_path = project_root / "logs" / "chat_transcript.jsonl"
            logs_path.parent.mkdir(parents=True, exist_ok=True)
            logs_path.write_text(
                "\n".join(
                    [
                        json.dumps(other_record, ensure_ascii=False),
                        json.dumps(matching_record, ensure_ascii=False),
                    ]
                ) + "\n",
                encoding="utf-8",
            )

            with patch.object(translator_views, "_project_root", str(project_root)), \
                 patch.object(translator_views, "_get_sim_log_start_time", return_value=None):
                records = translator_views._load_chat_transcript_records(sim_code, step=141, limit=12)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["dialogue_id"], "dlg_match")
        self.assertEqual(records[0]["conversation"][0]["utterance"], "match hello")


if __name__ == "__main__":
    unittest.main()
