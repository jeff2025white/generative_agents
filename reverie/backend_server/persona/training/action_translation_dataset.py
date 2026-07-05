"""
Dedicated action_translation SFT training dataset logger.

Writes complete (prompt, completion) pairs in ChatML/OpenAI format
for fine-tuning a local model to replace the cloud LLM on the
action_translation step.

Output: logs/training_dataset/action_translation_sft.jsonl
"""
import datetime
import json
import os

DATASET_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "logs", "training_dataset")
)
DATASET_PATH = os.path.join(DATASET_DIR, "action_translation_sft.jsonl")

SYSTEM_MESSAGE = (
    "You are a precise physical translation engine for a sandbox simulation. "
    "Your job is to translate the natural language intent of an agent into a "
    "standard physical command JSON object that the world physics engine can execute. "
    "Respond ONLY in valid JSON format with keys: action, target, detail, duration, reasoning."
)


def log_action_translation_pair(persona_name, prompt, decision, decision_id=None, step=None):
    """
    Write one complete (prompt, decision) training pair.

    Args:
        persona_name: The agent's first name (e.g. "Klaus").
        prompt: The full prompt string sent to the LLM.
        decision: The parsed decision dict returned by the LLM
                  (keys: action, target, detail, duration, reasoning).
        decision_id: Optional unique ID for this decision.
        step: Optional simulation step number.
    """
    if not prompt or not decision:
        return
    if not isinstance(decision, dict):
        return

    # Build the assistant completion as a clean JSON string
    completion_obj = {
        "action": decision.get("action", "Idle"),
        "target": decision.get("target", "none"),
        "detail": decision.get("detail", ""),
        "duration": decision.get("duration", 10),
        "reasoning": decision.get("reasoning", ""),
    }
    completion_str = json.dumps(completion_obj, ensure_ascii=False)

    record = {
        "messages": [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": completion_str},
        ],
        "metadata": {
            "persona": persona_name,
            "decision_id": decision_id,
            "step": step,
            "ts": datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(),
        },
    }

    os.makedirs(DATASET_DIR, exist_ok=True)
    with open(DATASET_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
