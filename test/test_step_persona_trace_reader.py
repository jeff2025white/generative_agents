import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from persona.log_analysis.step_persona_trace_reader import load_step_persona_trace


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


class StepPersonaTraceReaderTests(unittest.TestCase):
    def test_load_trace_aggregates_core_chain_for_step_persona(self):
        sim_code = "sim_20260710_113627"
        persona = "Maria Lopez"
        step = 42
        decision_id = "Maria-42-decision"

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            logs_root = project_root / "logs"
            _write_jsonl(
                logs_root / "decision_prompt_trace.jsonl",
                [
                    {
                        "sim_code": sim_code,
                        "persona": persona,
                        "curr_step": step,
                        "sim_time": "2026-07-10 08:05:00",
                        "event": "prompt_response",
                        "stage": "demand_thinking",
                        "stage_order": 10,
                        "decision_id": decision_id,
                        "llm_response": "I should gather food.",
                    },
                    {
                        "sim_code": sim_code,
                        "persona": persona,
                        "curr_step": step,
                        "sim_time": "2026-07-10 08:05:01",
                        "event": "final_decision",
                        "stage": "final_decision",
                        "stage_order": 30,
                        "decision_id": decision_id,
                        "decision_routed_action": "Gather",
                        "decision_routed_target": "refrigerator",
                        "decision_routed_detail": "opening the refrigerator",
                        "decision_routed_reasoning": "Satiety is low.",
                        "llm_decision_text": {"thought": "I should gather food."},
                    },
                ],
            )
            _write_jsonl(
                logs_root / "translation_verify.jsonl",
                [
                    {
                        "sim_code": sim_code,
                        "persona": persona,
                        "curr_step": step,
                        "sim_time": "2026-07-10 08:05:02",
                        "event": "decision_snapshot",
                        "decision_id": decision_id,
                        "intent": "I should gather food.",
                        "decision_routed_action": "Gather",
                        "decision_routed_target": "refrigerator",
                        "decision_routed_detail": "opening the refrigerator",
                        "decision_routed_reasoning": "Satiety is low.",
                    }
                ],
            )
            _write_jsonl(
                logs_root / "action_execution_debug.jsonl",
                [
                    {
                        "sim_code": sim_code,
                        "persona": persona,
                        "curr_step": step,
                        "sim_time": "2026-07-10 08:05:03",
                        "event": "path_set",
                    },
                    {
                        "sim_code": sim_code,
                        "persona": persona,
                        "curr_step": step,
                        "sim_time": "2026-07-10 08:05:04",
                        "event": "arrive",
                    },
                ],
            )
            _write_jsonl(
                logs_root / "action_outcome.jsonl",
                [
                    {
                        "sim_code": sim_code,
                        "persona": persona,
                        "curr_step": step,
                        "sim_time": "2026-07-10 08:05:05",
                        "event": "action_outcome",
                        "outcome": {
                            "outcome_id": "outcome-1",
                            "decision_context": {"decision_id": decision_id},
                            "action": {
                                "skill_id": "gather",
                                "target": "refrigerator",
                                "target_address": "the Ville:Dorm:shared kitchen:refrigerator",
                            },
                            "execution": {"result": "success", "reason": "resource_collected"},
                            "experience_scoring": {"progress_score": 0.85},
                        },
                    }
                ],
            )
            _write_jsonl(
                logs_root / "motive_monitor.jsonl",
                [
                    {
                        "sim_code": sim_code,
                        "persona": persona,
                        "curr_step": step,
                        "sim_time": "2026-07-10 08:05:06",
                        "event": "motive_delta",
                        "dominant_motive": "satiety",
                        "secondary_motive": "stamina",
                        "motive_sentence": "我很饿，我很想进食。",
                        "changed_motives": [{"motive": "satiety", "delta": 15.0}],
                    }
                ],
            )

            trace = load_step_persona_trace(sim_code, persona, step, project_root=str(project_root))

        self.assertFalse(trace["schema_incomplete"])
        self.assertEqual(trace["decision_summary"]["decision_id"], decision_id)
        self.assertEqual(trace["decision_summary"]["action"], "Gather")
        self.assertEqual(trace["action_outcome_summary"]["result"], "success")
        self.assertEqual(trace["action_outcome_summary"]["progress_score"], 0.85)
        self.assertEqual(trace["motive_summary"]["dominant_motive"], "satiety")
        self.assertIn(decision_id, trace["anchors"]["decision_ids"])
        self.assertEqual([entry["source"] for entry in trace["timeline"][:3]], ["decision_prompt", "decision_prompt", "translation"])

    def test_load_trace_skips_old_schema_records_in_strict_mode(self):
        sim_code = "sim_20260710_113627"
        persona = "Maria Lopez"
        step = 42

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            logs_root = project_root / "logs"
            _write_jsonl(
                logs_root / "action_execution_debug.jsonl",
                [
                    {
                        "persona": persona,
                        "event": "path_set",
                        "curr_step": step,
                    },
                    {
                        "sim_code": sim_code,
                        "persona": persona,
                        "curr_step": step,
                        "sim_time": "2026-07-10 08:05:03",
                        "event": "path_set",
                    },
                ],
            )

            trace = load_step_persona_trace(sim_code, persona, step, project_root=str(project_root), strict_schema=True)

        self.assertEqual(len(trace["timeline"]), 1)
        self.assertEqual(trace["timeline"][0]["record"]["sim_code"], sim_code)


if __name__ == "__main__":
    unittest.main()
