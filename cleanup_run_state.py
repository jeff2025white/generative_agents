#!/usr/bin/env python3
"""Clean transient state before starting a fresh simulation run."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LOGS_DIR = ROOT / "logs"
ROOT_TEMP_DIR = ROOT / "temp_storage"
FRONTEND_TEMP_DIR = ROOT / "environment" / "frontend_server" / "temp_storage"
FRONTEND_STORAGE_DIR = ROOT / "environment" / "frontend_server" / "storage"
DB_PATH = ROOT / "environment" / "frontend_server" / "db.sqlite3"
LLM_CACHE_PATH = ROOT / "reverie" / "backend_server" / ".prompt_cache" / "llm_cache.json"
TRANSLATION_CACHE_PATH = ROOT_TEMP_DIR / "translation_cache.json"

TRANSIENT_LOGS = [
    "action_execution_debug.jsonl",
    "chat_transcript.jsonl",
    "decision_prompt_trace.jsonl",
    "decision_stability.jsonl",
    "intent_memory_retrieval.jsonl",
    "ollama_request_timing.jsonl",
    "perception_debug.jsonl",
    "skill_execution_debug.jsonl",
    "social_dialogue_debug.jsonl",
    "social_trigger_debug.jsonl",
    "step_timing.jsonl",
    "translation_verify.jsonl",
]


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _truncate_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def _remove_if_exists(path: Path) -> bool:
    if not path.exists():
        return False
    path.unlink()
    return True


def reset_prompt_caches() -> list[str]:
    actions = []
    _write_json(LLM_CACHE_PATH, {})
    actions.append(str(LLM_CACHE_PATH))
    _write_json(TRANSLATION_CACHE_PATH, {})
    actions.append(str(TRANSLATION_CACHE_PATH))
    return actions


def reset_temp_state() -> list[str]:
    actions = []
    for temp_dir in [ROOT_TEMP_DIR, FRONTEND_TEMP_DIR]:
        if not temp_dir.exists():
            continue
        for name in ["curr_sim_code.json", "curr_step.json"]:
            if _remove_if_exists(temp_dir / name):
                actions.append(str(temp_dir / name))
        for heartbeat in temp_dir.glob("frontend_active_*.json"):
            heartbeat.unlink()
            actions.append(str(heartbeat))
    return actions


def reset_transient_logs() -> list[str]:
    actions = []
    for log_name in TRANSIENT_LOGS:
        path = LOGS_DIR / log_name
        _truncate_file(path)
        actions.append(str(path))
    return actions


def reset_scoped_chat_transcripts() -> list[str]:
    actions = []
    if not FRONTEND_STORAGE_DIR.exists():
        return actions

    for transcript_path in FRONTEND_STORAGE_DIR.glob("*/chat_transcript.jsonl"):
        _truncate_file(transcript_path)
        actions.append(str(transcript_path))
    return actions


def reset_frontend_db() -> list[str]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM translator_simstate")
        cur.execute("DELETE FROM translator_simpendingaction")
        conn.commit()
    finally:
        conn.close()
    return ["translator_simstate", "translator_simpendingaction"]


def main() -> int:
    touched = {
        "caches": reset_prompt_caches(),
        "temp_state": reset_temp_state(),
        "logs": reset_transient_logs(),
        "scoped_chat_logs": reset_scoped_chat_transcripts(),
        "db_tables": reset_frontend_db(),
    }
    print("[cleanup] transient run state cleared")
    for group, items in touched.items():
        print(f"[cleanup] {group}: {len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
