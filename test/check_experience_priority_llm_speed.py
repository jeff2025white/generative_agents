import json
import os
import sys
import time
import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(str(BACKEND_ROOT))

from persona.memory_structures.associative_memory import AssociativeMemory  # noqa: E402
from persona.memory_structures.scratch import Scratch  # noqa: E402
from persona.prompt_template.gpt_structure import generate_prompt  # noqa: E402
import persona.prompt_template.gpt_structure as gpt_structure  # noqa: E402
from persona.prompt_template.run_gpt_prompt import (  # noqa: E402
    run_gpt_prompt_action_translation,
    run_gpt_prompt_demand_thinking,
)


DEMAND_PROMPT_TEMPLATE = "persona/prompt_template/v2/demand_decision_thinking_v1.txt"
TRANSLATION_PROMPT_TEMPLATE = "persona/prompt_template/v2/action_translation_v1.txt"


class PersonaLite:
    def __init__(self, sim_code, persona_name):
        persona_dir = (
            ROOT
            / "environment"
            / "frontend_server"
            / "storage"
            / sim_code
            / "personas"
            / persona_name
            / "bootstrap_memory"
        )
        self.name = persona_name
        self.scratch = Scratch(str(persona_dir / "scratch.json"))
        self.a_mem = AssociativeMemory(str(persona_dir / "associative_memory"))
        self.s_mem = None
        for node in self.a_mem.seq_event + self.a_mem.seq_thought + self.a_mem.seq_chat:
            node.last_accessed = node.created or self.scratch.curr_time


def clear_prompt_cache():
    with gpt_structure._cache_lock:
        gpt_structure._cache.clear()
    cache_file = Path(gpt_structure._cache_file)
    if cache_file.exists():
        cache_file.unlink()


def build_prompt(persona, nearby_resources, temporal_context, status_summary,
                 rules, cooperative_context, last_action_desc, intent_memory_summary):
    inv_str = str(persona.scratch.inventory) if persona.scratch.inventory else "empty"
    res_str = ", ".join(nearby_resources) if nearby_resources else "no resources nearby"
    summary = intent_memory_summary or "No especially relevant prior experience was retrieved."

    prompt_input = [
        persona.scratch.get_str_iss(),
        f"{persona.scratch.satiety:.1f}",
        f"{persona.scratch.stamina:.1f}",
        f"{persona.scratch.health:.1f}",
        f"{persona.scratch.mood:.1f}",
        inv_str,
        res_str,
        temporal_context,
        status_summary,
        rules,
        cooperative_context,
        persona.scratch.get_str_firstname(),
        str(last_action_desc),
        summary,
    ]
    prompt = generate_prompt(prompt_input, DEMAND_PROMPT_TEMPLATE)

    special_instruction = (
        "State what you plan to do next in a simple, natural language sentence. "
        "Describe only the immediate next action, not a multi-step plan, and mention "
        "only one target object or location. Use the Homeostasis Interpretation, "
        "Behavioral Hints, Risks, and Overall Summary as your primary urgency guide. "
        "If those indicate that hunger, fatigue, injury, or emotional strain is "
        "becoming the most pressing issue, let that outweigh routine role goals. "
        "Treat the last action only as continuity context; do not infer that the "
        "agent is still especially tired, hurt, or committed to continuing it unless "
        "the current stats and status interpretation support that conclusion. Note: "
        "Daily plan requirements and lifestyle guidelines are non-binding. "
        "Prioritizing physiological needs is fully authorized."
    )
    if persona.scratch.satiety < 30.0:
        if not persona.scratch.inventory:
            special_instruction += (
                " CRITICAL: Satiety is critically low and inventory is empty! You MUST "
                "state that you plan to gather food from a valid nearby source like a "
                "refrigerator, stove, cafe counter, or apple tree first!"
            )
        else:
            food_item = next((k for k, v in persona.scratch.inventory.items() if v > 0), "food")
            special_instruction += (
                f" CRITICAL: Satiety is critically low! You MUST state that you plan "
                f"to eat/consume the {food_item} from your inventory immediately!"
            )
    elif persona.scratch.stamina < 30.0:
        special_instruction += " CRITICAL: Stamina is critically low! You MUST state that you plan to sleep or rest immediately!"

    return prompt + f"\n{special_instruction}\nAnswer:"


def build_translation_prompt(thinking_text, nearby_resources, firstname):
    schema_path = Path("persona") / "prompt_template" / "v2" / "action_schema.json"
    schema_str = schema_path.read_text(encoding="utf-8")
    res_str = ", ".join(nearby_resources) if nearby_resources else "no resources nearby"
    prompt_input = [
        thinking_text,
        schema_str,
        res_str,
        firstname,
    ]
    prompt = generate_prompt(prompt_input, TRANSLATION_PROMPT_TEMPLATE)
    special_instruction = "Select the best action, target, detail and duration based on intent and schema targets."
    return f"{prompt}\n{special_instruction}"


def benchmark_variant(persona, label, scenario_name, nearby_resources, temporal_context,
                      status_summary, rules, cooperative_context,
                      last_action_desc, intent_memory_summary,
                      benchmark_translation=False):
    clear_prompt_cache()
    demand_prompt = build_prompt(
        persona,
        nearby_resources,
        temporal_context,
        status_summary,
        rules,
        cooperative_context,
        last_action_desc,
        intent_memory_summary,
    )
    demand_started_at = time.perf_counter()
    thinking_text = run_gpt_prompt_demand_thinking(
        persona,
        nearby_resources,
        temporal_context=temporal_context,
        status_summary=status_summary,
        rules=rules,
        cooperative_context=cooperative_context,
        last_action_desc=last_action_desc,
        intent_memory_summary=intent_memory_summary,
    )
    demand_elapsed_ms = round((time.perf_counter() - demand_started_at) * 1000.0, 3)
    result = {
        "scenario": scenario_name,
        "label": label,
        "demand_prompt_chars": len(demand_prompt),
        "summary_chars": len(intent_memory_summary or ""),
        "thinking_text": thinking_text,
        "demand_duration_ms": demand_elapsed_ms,
    }
    if benchmark_translation:
        clear_prompt_cache()
        translation_prompt = build_translation_prompt(
            thinking_text,
            nearby_resources,
            persona.scratch.get_str_firstname(),
        )
        translation_started_at = time.perf_counter()
        translation_output = run_gpt_prompt_action_translation(
            thinking_text,
            nearby_resources,
            persona.scratch.get_str_firstname(),
        )
        translation_elapsed_ms = round((time.perf_counter() - translation_started_at) * 1000.0, 3)
        result["translation_prompt_chars"] = len(translation_prompt)
        result["translation_duration_ms"] = translation_elapsed_ms
        result["translation_output"] = translation_output
    return result


def make_persona(sim_code, persona_name, stat_overrides):
    persona = PersonaLite(sim_code, persona_name)
    persona.scratch.curr_step = 1
    if persona.scratch.curr_time is None:
        persona.scratch.curr_time = datetime.datetime(2023, 2, 13, 8, 0, 0)
    for key, value in (stat_overrides or {}).items():
        setattr(persona.scratch, key, value)
    return persona


def summarize_results(results, include_translation=False):
    without_items = [item for item in results if item["label"].startswith("without_memory")]
    with_items = [item for item in results if item["label"].startswith("with_memory")]

    payload = {
        "avg_without_demand_ms": round(sum(item["demand_duration_ms"] for item in without_items) / len(without_items), 3),
        "avg_with_demand_ms": round(sum(item["demand_duration_ms"] for item in with_items) / len(with_items), 3),
        "avg_without_demand_prompt_chars": round(sum(item["demand_prompt_chars"] for item in without_items) / len(without_items), 3),
        "avg_with_demand_prompt_chars": round(sum(item["demand_prompt_chars"] for item in with_items) / len(with_items), 3),
    }
    payload["demand_delta_ms"] = round(payload["avg_with_demand_ms"] - payload["avg_without_demand_ms"], 3)
    payload["demand_delta_percent"] = round(
        payload["demand_delta_ms"] / payload["avg_without_demand_ms"] * 100.0,
        3,
    ) if payload["avg_without_demand_ms"] else None

    if include_translation:
        payload["avg_without_translation_ms"] = round(
            sum(item["translation_duration_ms"] for item in without_items) / len(without_items),
            3,
        )
        payload["avg_with_translation_ms"] = round(
            sum(item["translation_duration_ms"] for item in with_items) / len(with_items),
            3,
        )
        payload["avg_without_translation_prompt_chars"] = round(
            sum(item["translation_prompt_chars"] for item in without_items) / len(without_items),
            3,
        )
        payload["avg_with_translation_prompt_chars"] = round(
            sum(item["translation_prompt_chars"] for item in with_items) / len(with_items),
            3,
        )
        payload["translation_delta_ms"] = round(
            payload["avg_with_translation_ms"] - payload["avg_without_translation_ms"],
            3,
        )
        payload["translation_delta_percent"] = round(
            payload["translation_delta_ms"] / payload["avg_without_translation_ms"] * 100.0,
            3,
        ) if payload["avg_without_translation_ms"] else None
    return payload


def run_scenario(sim_code, persona_name, scenario_name, config):
    results = []
    for run_index in range(2):
        persona = make_persona(sim_code, persona_name, config["stat_overrides"])
        temporal_context = (
            f"Current Time: {persona.scratch.curr_time.strftime('%A %B %d, %Y, %I:%M %p')} "
            f"[{scenario_name} benchmark run {run_index + 1}]"
        )
        results.append(
            benchmark_variant(
                persona,
                label=f"without_memory_run_{run_index + 1}",
                scenario_name=scenario_name,
                nearby_resources=config["nearby_resources"],
                temporal_context=temporal_context,
                status_summary=config["status_summary"],
                rules=config["rules"],
                cooperative_context=config["cooperative_context"],
                last_action_desc=config["last_action_desc"],
                intent_memory_summary=None,
                benchmark_translation=config.get("benchmark_translation", False),
            )
        )
        persona = make_persona(sim_code, persona_name, config["stat_overrides"])
        results.append(
            benchmark_variant(
                persona,
                label=f"with_memory_run_{run_index + 1}",
                scenario_name=scenario_name,
                nearby_resources=config["nearby_resources"],
                temporal_context=temporal_context,
                status_summary=config["status_summary"],
                rules=config["rules"],
                cooperative_context=config["cooperative_context"],
                last_action_desc=config["last_action_desc"],
                intent_memory_summary=config["memory_summary"],
                benchmark_translation=config.get("benchmark_translation", False),
            )
        )
    return {
        "scenario": scenario_name,
        "persona": persona_name,
        "memory_summary": config["memory_summary"],
        "results": results,
        "summary": summarize_results(results, include_translation=config.get("benchmark_translation", False)),
    }


def main():
    sim_code = "sim_20260702_095858_expcheck"
    persona_name = "Maria Lopez"
    scenarios = {
        "restore_satiety": {
            "stat_overrides": {"satiety": 18.0, "stamina": 82.0, "health": 92.0, "mood": 68.0, "inventory": {}},
            "nearby_resources": ["refrigerator", "stove", "apple tree", "cafe counter"],
            "status_summary": (
                "Satiety is critically low while the inventory is empty. Hunger should take "
                "priority over routine plans until food is secured."
            ),
            "rules": (
                "If satiety is low, prioritize actions that can restore satiety quickly. "
                "Prefer known, nearby, and previously successful food sources."
            ),
            "cooperative_context": "No special cooperative request is active nearby.",
            "last_action_desc": "Walking around campus",
            "memory_summary": "\n".join(
                [
                    "Relevant prior food-related experience:",
                    "- Maria Lopez consumed a cooked meal and recovered from hunger quickly.",
                    "- Maria Lopez gathered apples from the refrigerator and restored her satiety effectively.",
                ]
            ),
            "benchmark_translation": True,
        },
        "restore_health": {
            "stat_overrides": {"satiety": 72.0, "stamina": 58.0, "health": 34.0, "mood": 52.0, "inventory": {}},
            "nearby_resources": ["bed", "sofa", "desk", "refrigerator"],
            "status_summary": (
                "Health is critically low. Physical recovery and avoiding further strain should "
                "take priority over routine tasks."
            ),
            "rules": (
                "If health is low, prefer restorative and low-risk actions. Consider rest and "
                "safer recovery choices before work."
            ),
            "cooperative_context": "No special cooperative request is active nearby.",
            "last_action_desc": "Working continuously despite discomfort",
            "memory_summary": "\n".join(
                [
                    "Relevant prior health-related experience:",
                    "- Maria Lopez rested carefully and recovered her health after treatment.",
                    "- Maria Lopez felt physically worse when she kept working through pain.",
                ]
            ),
            "benchmark_translation": False,
        },
        "restore_mood": {
            "stat_overrides": {"satiety": 70.0, "stamina": 66.0, "health": 84.0, "mood": 24.0, "inventory": {}},
            "nearby_resources": ["sofa", "tv", "piano", "cafe counter"],
            "status_summary": (
                "Mood is very low. Emotional recovery should take priority over demanding tasks "
                "until the agent stabilizes."
            ),
            "rules": (
                "If mood is low, prefer comforting, social, or restorative leisure activities "
                "that have worked before."
            ),
            "cooperative_context": "No special cooperative request is active nearby.",
            "last_action_desc": "Pushing through a stressful day alone",
            "memory_summary": "\n".join(
                [
                    "Relevant prior mood-related experience:",
                    "- Maria Lopez sang for a while and felt more energetic and upbeat.",
                    "- Maria Lopez felt calmer after taking a short break on the sofa.",
                ]
            ),
            "benchmark_translation": False,
        },
    }

    scenario_payloads = {
        scenario_name: run_scenario(sim_code, persona_name, scenario_name, config)
        for scenario_name, config in scenarios.items()
    }
    payload = {
        "sim_code": sim_code,
        "persona": persona_name,
        "scenarios": scenario_payloads,
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
