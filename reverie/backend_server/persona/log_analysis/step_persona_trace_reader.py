import argparse
import json
import os
from collections import defaultdict


TRACE_LOG_SPECS = (
    {
        "key": "perception",
        "log_name": "perception_debug.jsonl",
        "event_types": {"perceive_summary"},
        "stage_order": 5,
    },
    {
        "key": "intent_memory",
        "log_name": "intent_memory_retrieval.jsonl",
        "event_types": None,
        "stage_order": 8,
    },
    {
        "key": "decision_prompt",
        "log_name": "decision_prompt_trace.jsonl",
        "event_types": {"prompt_response", "final_decision"},
        "stage_order": None,
    },
    {
        "key": "translation",
        "log_name": "translation_verify.jsonl",
        "event_types": {
            "coerce_consume_source_to_gather",
            "retarget_invalid_food_source",
            "decision_snapshot",
            "decision_cache_store",
            "target_resolution",
        },
        "stage_order": 35,
    },
    {
        "key": "decision_stability",
        "log_name": "decision_stability.jsonl",
        "event_types": None,
        "stage_order": 40,
    },
    {
        "key": "execution",
        "log_name": "action_execution_debug.jsonl",
        "event_types": None,
        "stage_order": 50,
    },
    {
        "key": "action_outcome",
        "log_name": "action_outcome.jsonl",
        "event_types": None,
        "stage_order": 60,
    },
    {
        "key": "motive_monitor",
        "log_name": "motive_monitor.jsonl",
        "event_types": {"motive_delta"},
        "stage_order": 70,
    },
    {
        "key": "step_timing",
        "log_name": "step_timing.jsonl",
        "event_types": {"persona_move_timing", "decide_demand_action_timing", "backend_step_timing"},
        "stage_order": 90,
    },
)


def _project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


def _logs_dir(project_root=None):
    root = project_root or _project_root()
    return os.path.join(root, "logs")


def _normalize_persona(persona_name):
    return str(persona_name or "").strip()


def _normalize_step(step):
    if step is None:
        return None
    try:
        return int(step)
    except Exception:
        return None


def _iter_jsonl_records(path):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def _matches_schema(record):
    return bool(record.get("sim_code")) and (
        record.get("curr_step") is not None or record.get("step") is not None
    )


def _record_step(record):
    return _normalize_step(record.get("curr_step", record.get("step")))


def _record_persona(record):
    return _normalize_persona(record.get("persona"))


def _extract_decision_id(record):
    decision_id = record.get("decision_id")
    if decision_id:
        return decision_id
    outcome = record.get("outcome") or {}
    if isinstance(outcome, dict):
        context = outcome.get("decision_context") or {}
        if isinstance(context, dict):
            return context.get("decision_id")
    state = record.get("state") or {}
    if isinstance(state, dict):
        action_record = state.get("action_record") or {}
        if isinstance(action_record, dict):
            return action_record.get("decision_id")
    return None


def _extract_dialogue_id(record):
    return record.get("dialogue_id")


def _infer_stage_order(spec, record):
    if spec["key"] == "decision_prompt":
        return int(record.get("stage_order", 99) or 99)
    return spec["stage_order"] if spec["stage_order"] is not None else 99


def _build_timeline_entry(spec, record):
    return {
        "source": spec["key"],
        "log": spec["log_name"],
        "event": record.get("event"),
        "stage": record.get("stage") or spec["key"],
        "stage_order": _infer_stage_order(spec, record),
        "ts": record.get("ts"),
        "sim_time": record.get("sim_time"),
        "curr_step": _record_step(record),
        "persona": _record_persona(record),
        "decision_id": _extract_decision_id(record),
        "dialogue_id": _extract_dialogue_id(record),
        "record": record,
    }


def _summarize_decision(entries):
    for entry in entries:
        record = entry["record"]
        if record.get("event") == "decision_snapshot":
            return {
                "decision_id": record.get("decision_id"),
                "intent": record.get("intent"),
                "action": record.get("decision_routed_action"),
                "target": record.get("decision_routed_target"),
                "detail": record.get("decision_routed_detail"),
                "reasoning": record.get("decision_routed_reasoning"),
            }
        if record.get("event") == "final_decision":
            return {
                "decision_id": record.get("decision_id"),
                "intent": (record.get("llm_decision_text") or {}).get("thought"),
                "action": record.get("decision_routed_action"),
                "target": record.get("decision_routed_target"),
                "detail": record.get("decision_routed_detail"),
                "reasoning": record.get("decision_routed_reasoning"),
            }
    return {}


def _summarize_action_outcome(entries):
    for entry in entries:
        record = entry["record"]
        if entry["source"] != "action_outcome":
            continue
        outcome = record.get("outcome") or {}
        if not isinstance(outcome, dict):
            continue
        action = outcome.get("action") or {}
        execution = outcome.get("execution") or {}
        scoring = outcome.get("experience_scoring") or {}
        return {
            "outcome_id": outcome.get("outcome_id"),
            "result": execution.get("result"),
            "reason": execution.get("reason"),
            "skill_id": action.get("skill_id"),
            "target": action.get("target"),
            "target_address": action.get("target_address"),
            "progress_score": scoring.get("progress_score"),
            "decision_id": (outcome.get("decision_context") or {}).get("decision_id"),
        }
    return {}


def _summarize_motive(entries):
    motive_entries = [entry for entry in entries if entry["source"] == "motive_monitor"]
    if not motive_entries:
        return {}
    latest = motive_entries[-1]["record"]
    return {
        "dominant_motive": latest.get("dominant_motive"),
        "secondary_motive": latest.get("secondary_motive"),
        "motive_sentence": latest.get("motive_sentence"),
        "changed_motives": latest.get("changed_motives", []),
    }


def _detect_missing_stages(grouped_entries):
    missing = []
    required = [
        "decision_prompt",
        "translation",
        "execution",
        "action_outcome",
    ]
    for key in required:
        if not grouped_entries.get(key):
            missing.append(key)
    return missing


def load_step_persona_trace(sim_code, persona_name, step, project_root=None, strict_schema=True):
    persona_name = _normalize_persona(persona_name)
    step = _normalize_step(step)
    trace = {
        "schema_version": 1,
        "sim_code": sim_code,
        "persona": persona_name,
        "curr_step": step,
        "strict_schema": bool(strict_schema),
        "timeline": [],
        "grouped": {},
        "decision_summary": {},
        "action_outcome_summary": {},
        "motive_summary": {},
        "anchors": {
            "decision_ids": [],
            "dialogue_ids": [],
        },
        "missing_stages": [],
        "schema_incomplete": False,
    }

    if not sim_code or not persona_name or step is None:
        trace["schema_incomplete"] = True
        trace["missing_stages"] = ["invalid_request"]
        return trace

    logs_dir = _logs_dir(project_root=project_root)
    grouped = defaultdict(list)
    decision_ids = set()
    dialogue_ids = set()

    for spec in TRACE_LOG_SPECS:
        path = os.path.join(logs_dir, spec["log_name"])
        for record in _iter_jsonl_records(path):
            if strict_schema and not _matches_schema(record):
                continue
            if str(record.get("sim_code", "") or "").strip() != str(sim_code).strip():
                continue
            if _record_persona(record) != persona_name:
                continue
            if _record_step(record) != step:
                continue
            if spec["event_types"] and record.get("event") not in spec["event_types"]:
                continue

            entry = _build_timeline_entry(spec, record)
            grouped[spec["key"]].append(entry)
            trace["timeline"].append(entry)
            if entry["decision_id"]:
                decision_ids.add(entry["decision_id"])
            if entry["dialogue_id"]:
                dialogue_ids.add(entry["dialogue_id"])

    trace["timeline"].sort(
        key=lambda item: (
            int(item.get("stage_order", 999) or 999),
            str(item.get("sim_time", "") or ""),
            str(item.get("ts", "") or ""),
        )
    )
    trace["grouped"] = {key: value for key, value in grouped.items()}
    trace["anchors"]["decision_ids"] = sorted(decision_ids)
    trace["anchors"]["dialogue_ids"] = sorted(dialogue_ids)
    trace["decision_summary"] = _summarize_decision(trace["timeline"])
    trace["action_outcome_summary"] = _summarize_action_outcome(trace["timeline"])
    trace["motive_summary"] = _summarize_motive(trace["timeline"])
    trace["missing_stages"] = _detect_missing_stages(trace["grouped"])
    return trace


def _build_cli_parser():
    parser = argparse.ArgumentParser(description="Load a run-scoped step-persona trace from JSONL logs.")
    parser.add_argument("--sim-code", required=True)
    parser.add_argument("--persona", required=True)
    parser.add_argument("--step", required=True, type=int)
    parser.add_argument("--project-root", default=None)
    return parser


def main():
    parser = _build_cli_parser()
    args = parser.parse_args()
    trace = load_step_persona_trace(
        sim_code=args.sim_code,
        persona_name=args.persona,
        step=args.step,
        project_root=args.project_root,
        strict_schema=True,
    )
    print(json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
