"""Simulate a longer NPC small-talk conversation without requiring a fixed topic."""

import argparse
import io
import json
import os
import sys
from contextlib import contextmanager
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from llm_api_config import get_default_social_chat_request_config
from persona.cognitive_modules.retrieve import new_retrieve
from persona.cognitive_modules.skill_packs.chat_skill import (
    collect_social_chat_memory_keys,
    filter_social_chat_recent_events,
    is_structurally_valid_social_chat_response,
    normalize_social_chat_response,
    sanitize_social_chat_utterance,
)
from persona.persona import Persona
from persona.prompt_template.gpt_structure import ChatGPT_request, clean_json_str


TIME_FORMAT = "%B %d, %Y, %H:%M:%S"
SOCIAL_CHAT_REQUEST_CONFIG = get_default_social_chat_request_config()
DEFAULT_SIM_PATH = ROOT / "environment" / "frontend_server" / "storage" / "sim_20260704_175105"

SMALLTALK_PROMPT_TEMPLATE = """You are {speaker_iss}.
You are casually chatting with {listener_name}.

Current context:
{speaker_context}

Relevant memories you can naturally draw from:
{memories_text}

Conversation history:
{history_text}

Small-talk guidance:
- You do NOT need a fixed topic.
- If nothing special is happening, casually react to the current moment, nearby place, recent activity, mood, food, weather, rumors, or the other person's last line.
- Keep the chat feeling natural and lightweight. It is okay to just greet, check in, make a small observation, or continue a loose thread.
- Avoid forcing a dramatic rumor or a strong plot point every turn.
- Stay in casual spoken Simplified Chinese.
- Keep each line short: ideally one sentence, at most two short sentences.
- Maintain conversational momentum by either asking a light follow-up, sharing a tiny observation, or softly closing the loop.
- Only end the chat when it feels natural after enough back-and-forth, not immediately.

Task:
Write the next utterance as {speaker_first_name}.

Respond ONLY in valid JSON:
{{
  "utterance": "<brief colloquial Chinese dialogue>",
  "end": <true/false>,
  "reasoning": "<brief strategy note>"
}}"""


class FallbackMaze:
    """Provide the minimal maze API needed by the chat simulation."""

    def __init__(self, arena_name):
        self.arena_name = arena_name

    def get_tile_path(self, tile, level):
        _ = tile
        _ = level
        return self.arena_name


@contextmanager
def pushd(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def read_json(file_path):
    return json.loads(Path(file_path).read_text(encoding="utf-8"))


def parse_sim_time(raw_value):
    if not raw_value:
        return None
    return datetime.strptime(raw_value, TIME_FORMAT)


def find_snapshot_at_or_before(directory, preferred_step=None):
    candidates = []
    for item in Path(directory).glob("*.json"):
        try:
            candidates.append((int(item.stem), item))
        except ValueError:
            continue
    if not candidates:
        return None, None
    if preferred_step is None:
        return max(candidates, key=lambda entry: entry[0])
    eligible = [entry for entry in candidates if entry[0] <= preferred_step]
    if eligible:
        return max(eligible, key=lambda entry: entry[0])
    return min(candidates, key=lambda entry: entry[0])


def load_meta(sim_path):
    return read_json(Path(sim_path) / "reverie" / "meta.json")


def select_environment_snapshot(sim_path, preferred_step=None):
    env_dir = Path(sim_path) / "environment"
    step, file_path = find_snapshot_at_or_before(env_dir, preferred_step)
    if file_path is None:
        return None, {}
    return step, read_json(file_path)


def select_reference_movement_snapshot(sim_path, preferred_step=None):
    movement_dir = Path(sim_path) / "movement"
    step, file_path = find_snapshot_at_or_before(movement_dir, preferred_step)
    if file_path is None:
        return None, {}
    return step, read_json(file_path)


def load_persona_from_sim(sim_path, persona_name):
    persona_dir = Path(sim_path) / "personas" / persona_name
    if not persona_dir.exists():
        raise FileNotFoundError(f"Cannot find persona directory: {persona_dir}")
    return Persona(persona_name, str(persona_dir))


def sync_persona_runtime_state(persona, env_snapshot, sim_time, step):
    if sim_time is not None:
        persona.scratch.curr_time = sim_time
    persona.scratch.curr_step = step
    env_entry = env_snapshot.get(persona.name)
    if env_entry:
        persona.scratch.curr_tile = [env_entry.get("x"), env_entry.get("y")]


def build_maze(meta):
    maze_name = meta.get("maze_name", "the_ville")
    try:
        with pushd(BACKEND_ROOT):
            from maze import Maze

            return Maze(maze_name), "real"
    except Exception as exc:
        return FallbackMaze(maze_name), f"fallback:{exc}"


def dedupe_preserve_order(values):
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def build_turn_context(speaker, listener, maze, convo, seed_topic=""):
    focal_points = [listener.name, "weather", "food", "today", "town"]
    if seed_topic:
        focal_points.insert(1, seed_topic)
    with redirect_stdout(io.StringIO()):
        retrieved = new_retrieve(speaker, focal_points, 10)

    memory_keys, dropped_memory_keys = collect_social_chat_memory_keys(retrieved)
    memory_keys = dedupe_preserve_order(memory_keys)[:6]
    memories_text = "\n".join(f"- {item}" for item in memory_keys) if memory_keys else "- none"

    history_text = "\n".join(f"{turn_speaker}: {utterance}" for turn_speaker, utterance in convo)
    if not history_text:
        history_text = "No conversation started yet."

    relationship = speaker.a_mem.get_relationship(listener.name)
    dropped_recent_events = []
    relation_text = ""
    if relationship:
        relation_text = (
            f" Relation status: {relationship.get('relationship', 'acquaintance')} "
            f"(Trust level: {relationship.get('trust', 0.5):.2f})."
        )
        recent_events, dropped_recent_events = filter_social_chat_recent_events(
            relationship.get("recent_events", [])
        )
        if recent_events:
            relation_text += f" Recent interactions: {', '.join(recent_events)}."

    arena = maze.get_tile_path(speaker.scratch.curr_tile, "arena")
    speaker_context = f"{speaker.name} and {listener.name} ran into each other in the {arena}.{relation_text}"
    prompt = SMALLTALK_PROMPT_TEMPLATE.format(
        speaker_iss=speaker.scratch.get_str_iss(),
        listener_name=listener.name,
        speaker_context=speaker_context,
        memories_text=memories_text,
        history_text=history_text,
        speaker_first_name=speaker.scratch.first_name,
    )
    return {
        "focal_points": focal_points,
        "memory_keys": memory_keys,
        "dropped_memory_keys": dropped_memory_keys,
        "dropped_recent_events": dropped_recent_events,
        "speaker_context": speaker_context,
        "history_text": history_text,
        "prompt": prompt,
    }


def build_wrapped_prompt(prompt):
    example_output = '{"utterance": "刚好碰见你，你今天看起来精神还不错。", "end": false, "reasoning": "casual check-in"}'
    wrapped_prompt = '"""\n' + prompt + '\n"""\n'
    wrapped_prompt += (
        "Output the response to the prompt above in json. "
        "Use colloquial Simplified Chinese. Keep it short and natural.\n"
    )
    wrapped_prompt += "Example output json:\n"
    wrapped_prompt += json.dumps({"output": example_output})
    return wrapped_prompt


def generate_live_turn(prompt, turn_index, total_turns):
    fail_safe = {
        "utterance": "刚好碰见你，随便聊两句。" if turn_index == 0 else "也是，慢慢来就好。",
        "end": turn_index >= total_turns - 1,
    }
    wrapped_prompt = build_wrapped_prompt(prompt)
    attempts = []

    for attempt_index in range(3):
        raw_response = ""
        attempt = {"attempt": attempt_index + 1}
        try:
            raw_response = ChatGPT_request(
                wrapped_prompt,
                prompt_kind="social_chat_smalltalk_debug",
                metadata={
                    "source": "check_simulate_npc_smalltalk",
                    "turn_index": turn_index,
                    "attempt": attempt_index + 1,
                },
                request_config=SOCIAL_CHAT_REQUEST_CONFIG,
            )
            attempt["raw_response"] = raw_response
            cleaned = clean_json_str(raw_response)
            attempt["cleaned_response"] = cleaned
            end_index = cleaned.rfind("}") + 1
            json_candidate = cleaned[:end_index] if end_index > 0 else cleaned
            attempt["json_candidate"] = json_candidate
            data = json.loads(json_candidate)
            parsed = data["output"] if isinstance(data, dict) and "output" in data else data
            if isinstance(parsed, str):
                try:
                    parsed = json.loads(parsed)
                except Exception:
                    pass
            attempt["parsed_response"] = parsed
            valid = is_structurally_valid_social_chat_response(parsed)
            attempt["valid"] = bool(valid)
            attempts.append(attempt)
            if valid:
                normalized = normalize_social_chat_response(
                    parsed,
                    fail_safe,
                    request_config=SOCIAL_CHAT_REQUEST_CONFIG,
                )
                attempt["normalized_response"] = normalized
                return normalized, {
                    "wrapped_prompt": wrapped_prompt,
                    "attempts": attempts,
                    "used_fail_safe": normalized == fail_safe,
                }
        except Exception as exc:
            attempt["raw_response"] = raw_response
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            attempt["valid"] = False
            attempts.append(attempt)

    return fail_safe, {
        "wrapped_prompt": wrapped_prompt,
        "attempts": attempts,
        "used_fail_safe": True,
    }


def simulate_smalltalk(initiator, target, maze, max_turns=20, seed_topic=""):
    convo = []
    trace = []
    speaker = initiator
    listener = target

    for turn_index in range(max_turns):
        context = build_turn_context(speaker, listener, maze, convo, seed_topic=seed_topic)
        decision, live_debug = generate_live_turn(context["prompt"], turn_index, max_turns)
        final_utterance = sanitize_social_chat_utterance(
            decision.get("utterance", "..."),
            turn_index,
            speaker,
            listener,
            convo,
        )
        decision["utterance"] = final_utterance

        force_continue = turn_index < max_turns - 2
        if force_continue:
            decision["end"] = False

        convo.append([speaker.name, final_utterance])
        trace.append(
            {
                "turn": turn_index,
                "speaker": speaker.name,
                "listener": listener.name,
                "context": context,
                "decision": decision,
                "live_debug": live_debug,
            }
        )

        if decision.get("end", False) and not force_continue:
            break
        speaker, listener = listener, speaker

    return convo, trace


def print_trace(convo, trace, maze_mode, show_prompt=False):
    print(f"maze_mode: {maze_mode}")
    print(f"turn_count: {len(convo)}")
    print("\n=== Transcript ===")
    for index, (speaker, utterance) in enumerate(convo, start=1):
        print(f"{index:02d}. {speaker}: {utterance}")

    print("\n=== Per-turn prompt summary ===")
    for item in trace:
        context = item["context"]
        print(f"\n[Turn {item['turn']}] {item['speaker']} -> {item['listener']}")
        print(f"focal_points: {context['focal_points']}")
        print("memory_keys:")
        if context["memory_keys"]:
            for memory in context["memory_keys"]:
                print(f"- {memory}")
        else:
            print("- none")
        if context["dropped_memory_keys"]:
            print("dropped_memory_keys:")
            for memory in context["dropped_memory_keys"]:
                print(f"- {memory}")
        if context["dropped_recent_events"]:
            print("dropped_recent_events:")
            for event in context["dropped_recent_events"]:
                print(f"- {event}")
        print(f"utterance: {item['decision'].get('utterance', '')}")
        print(f"end: {bool(item['decision'].get('end', False))}")
        print(f"used_fail_safe: {item['live_debug'].get('used_fail_safe', False)}")
        if show_prompt:
            print("prompt:")
            print(context["prompt"])


def build_argument_parser():
    parser = argparse.ArgumentParser(description="Simulate 20 turns of NPC small talk.")
    parser.add_argument("--sim-path", default=str(DEFAULT_SIM_PATH), help="Simulation storage directory.")
    parser.add_argument("--initiator", default="Maria Lopez", help="Initiator persona name.")
    parser.add_argument("--target", default="Klaus Mueller", help="Target persona name.")
    parser.add_argument("--step", type=int, default=None, help="Reference environment/movement step.")
    parser.add_argument("--max-turns", type=int, default=20, help="Maximum number of utterances to generate.")
    parser.add_argument("--seed-topic", default="", help="Optional loose topic hint, but not required.")
    parser.add_argument("--show-prompt", action="store_true", help="Print the full prompt for every turn.")
    return parser


def main():
    parser = build_argument_parser()
    args = parser.parse_args()

    sim_path = Path(args.sim_path)
    meta = load_meta(sim_path)
    movement_step, movement_snapshot = select_reference_movement_snapshot(sim_path, args.step)
    env_step, env_snapshot = select_environment_snapshot(sim_path, args.step)
    sim_time = parse_sim_time(movement_snapshot.get("meta", {}).get("curr_time") or meta.get("curr_time"))

    initiator = load_persona_from_sim(sim_path, args.initiator)
    target = load_persona_from_sim(sim_path, args.target)
    sync_persona_runtime_state(initiator, env_snapshot, sim_time, movement_step or env_step)
    sync_persona_runtime_state(target, env_snapshot, sim_time, movement_step or env_step)
    maze, maze_mode = build_maze(meta)

    print(f"sim_path: {sim_path}")
    print(f"movement_step: {movement_step}")
    print(f"environment_step: {env_step}")
    print(f"sim_time: {sim_time}")
    print(f"initiator: {initiator.name}")
    print(f"target: {target.name}")
    print(f"seed_topic: {args.seed_topic or '(none)'}")

    convo, trace = simulate_smalltalk(
        initiator=initiator,
        target=target,
        maze=maze,
        max_turns=args.max_turns,
        seed_topic=args.seed_topic,
    )
    print_trace(convo, trace, maze_mode, show_prompt=args.show_prompt)


if __name__ == "__main__":
    main()
