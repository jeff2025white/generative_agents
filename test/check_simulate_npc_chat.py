"""Replay and simulate an NPC-to-NPC chat from stored simulation data."""

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


from persona.persona import Persona
from persona.cognitive_modules.retrieve import new_retrieve
from llm_api_config import get_default_social_chat_request_config
from persona.cognitive_modules.skill_packs.chat_skill import (
    collect_social_chat_memory_keys,
    filter_social_chat_recent_events,
    is_structurally_valid_social_chat_response,
    is_valid_social_chat_response,
    normalize_social_chat_response,
)
from persona.prompt_template.gpt_structure import ChatGPT_request, clean_json_str, generate_prompt


TIME_FORMAT = "%B %d, %Y, %H:%M:%S"
CHAT_PROMPT_TEMPLATE = str(BACKEND_ROOT / "persona" / "prompt_template" / "v2" / "social_chat_gossip_v1.txt")
SOCIAL_CHAT_REQUEST_CONFIG = get_default_social_chat_request_config()


class FallbackMaze:
    """Provide the minimal maze API needed by the chat simulation."""

    def __init__(self, arena_name):
        self.arena_name = arena_name

    def get_tile_path(self, tile, level):
        """Return a readable arena label for prompt construction."""
        _ = tile
        _ = level
        return self.arena_name


@contextmanager
def pushd(path):
    """Temporarily switch the current working directory."""
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def read_json(file_path):
    """Load a JSON file from disk."""
    return json.loads(Path(file_path).read_text(encoding="utf-8"))


def parse_sim_time(raw_value):
    """Parse the simulation time string into a datetime object."""
    if not raw_value:
        return None
    return datetime.strptime(raw_value, TIME_FORMAT)


def find_latest_numbered_json(directory):
    """Return the highest numbered JSON file inside a snapshot directory."""
    candidates = []
    for item in Path(directory).glob("*.json"):
        try:
            candidates.append((int(item.stem), item))
        except ValueError:
            continue
    if not candidates:
        return None, None
    step, file_path = max(candidates, key=lambda entry: entry[0])
    return step, file_path


def find_snapshot_at_or_before(directory, preferred_step):
    """Return the nearest numbered snapshot file at or before a target step."""
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
    """Load the simulation metadata file."""
    return read_json(Path(sim_path) / "reverie" / "meta.json")


def select_reference_step(sim_path, requested_step=None):
    """Resolve the movement snapshot step used as the reference transcript."""
    movement_dir = Path(sim_path) / "movement"
    if requested_step is None:
        step, file_path = find_latest_numbered_json(movement_dir)
    else:
        file_path = movement_dir / f"{requested_step}.json"
        step = requested_step if file_path.exists() else None
    if step is None or file_path is None or not file_path.exists():
        raise FileNotFoundError(f"Cannot find movement snapshot for step={requested_step} under {movement_dir}")
    return step, read_json(file_path)


def select_environment_snapshot(sim_path, preferred_step=None):
    """Load the nearest environment snapshot for persona positions."""
    env_dir = Path(sim_path) / "environment"
    step, file_path = find_snapshot_at_or_before(env_dir, preferred_step)
    if file_path is None:
        return None, {}
    return step, read_json(file_path)


def extract_reference_chat(movement_snapshot, initiator, target):
    """Extract the recorded conversation from a movement snapshot."""
    persona_block = movement_snapshot.get("persona", {})
    for name in (initiator, target):
        entry = persona_block.get(name, {})
        chat = entry.get("chat")
        if chat:
            return chat
    return []


def load_persona_from_sim(sim_path, persona_name):
    """Load a persona object from a saved simulation directory."""
    persona_dir = Path(sim_path) / "personas" / persona_name
    if not persona_dir.exists():
        raise FileNotFoundError(f"Cannot find persona directory: {persona_dir}")
    return Persona(persona_name, str(persona_dir))


def sync_persona_runtime_state(persona, env_snapshot, sim_time, step):
    """Update transient persona state from the selected snapshots."""
    if sim_time is not None:
        persona.scratch.curr_time = sim_time
    persona.scratch.curr_step = step
    env_entry = env_snapshot.get(persona.name)
    if env_entry:
        persona.scratch.curr_tile = [env_entry.get("x"), env_entry.get("y")]


def build_maze(meta):
    """Build a real maze when possible, otherwise fall back to a stub."""
    maze_name = meta.get("maze_name", "the_ville")
    try:
        with pushd(BACKEND_ROOT):
            from maze import Maze

            return Maze(maze_name), "real"
    except Exception as exc:
        return FallbackMaze(maze_name), f"fallback:{exc}"


def dedupe_preserve_order(values):
    """Remove duplicates while keeping the first-seen ordering."""
    output = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def build_turn_context(speaker, listener, maze, convo):
    """Assemble the retrieval and prompt context for one social turn."""
    focal_points = [listener.name, "news", "rumor", "town"]
    with redirect_stdout(io.StringIO()):
        retrieved = new_retrieve(speaker, focal_points, 10)
    memory_keys, dropped_memory_keys = collect_social_chat_memory_keys(retrieved)
    memory_keys = dedupe_preserve_order(memory_keys)[:5]
    memories_text = "\n".join(f"- {item}" for item in memory_keys) if memory_keys else "- none"

    history_text = ""
    for turn_speaker, utterance in convo:
        history_text += f"{turn_speaker}: {utterance}\n"

    relationship = speaker.a_mem.get_relationship(listener.name)
    relation_text = ""
    dropped_recent_events = []
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

    current_context = f"{speaker.name} and {listener.name} met in the {maze.get_tile_path(speaker.scratch.curr_tile, 'arena')}."
    speaker_context = f"{current_context}{relation_text}"
    prompt_input = [
        speaker.scratch.get_str_iss(),
        listener.name,
        memories_text,
        speaker_context,
        history_text if history_text else "No conversation started yet.",
        speaker.scratch.first_name,
    ]
    prompt = generate_prompt(prompt_input, CHAT_PROMPT_TEMPLATE)
    return {
        "focal_points": focal_points,
        "memory_keys": memory_keys,
        "history_text": history_text if history_text else "No conversation started yet.",
        "speaker_context": speaker_context,
        "prompt": prompt,
        "dropped_memory_keys": dropped_memory_keys,
        "dropped_recent_events": dropped_recent_events,
    }


def build_wrapped_chat_prompt(prompt):
    """Wrap a plain prompt using the same JSON envelope as safe generation."""
    example_output = '{"utterance": "你听说Isabella最近研发了新的咖啡吗？听说味道特别棒！", "end": false, "reasoning": "Spreading a nice rumor about Isabella"}'
    special_instruction = "Provide valid JSON containing utterance and end. The utterance must be colloquial Simplified Chinese, never English."
    wrapped_prompt = '"""\n' + prompt + '\n"""\n'
    wrapped_prompt += f"Output the response to the prompt above in json. {special_instruction}\n"
    wrapped_prompt += "Example output json:\n"
    wrapped_prompt += '{"output": "' + example_output + '"}'
    return wrapped_prompt


def generate_live_turn(prompt, turn_index, repeat=3):
    """Run the real LLM-backed social turn generation with per-attempt diagnostics."""

    fail_safe = {
        "utterance": "你好！" if turn_index == 0 else "是的，我也这么觉得。",
        "end": True if turn_index >= 3 else False,
    }
    wrapped_prompt = build_wrapped_chat_prompt(prompt)
    attempts = []

    for attempt_index in range(repeat):
        raw_response = ""
        attempt_record = {"attempt": attempt_index + 1}
        try:
            raw_response = ChatGPT_request(
                wrapped_prompt,
                prompt_kind="social_chat_debug",
                metadata={"source": "check_simulate_npc_chat", "turn_index": turn_index, "attempt": attempt_index + 1},
                request_config=SOCIAL_CHAT_REQUEST_CONFIG,
            )
            attempt_record["raw_response"] = raw_response
            cleaned_response = clean_json_str(raw_response)
            attempt_record["cleaned_response"] = cleaned_response
            end_index = cleaned_response.rfind("}") + 1
            json_candidate = cleaned_response[:end_index] if end_index > 0 else cleaned_response
            attempt_record["json_candidate"] = json_candidate
            data = json.loads(json_candidate)
            parsed_response = data["output"] if isinstance(data, dict) and "output" in data else data
            attempt_record["parsed_response"] = parsed_response
            is_valid = is_structurally_valid_social_chat_response(parsed_response)
            attempt_record["valid"] = bool(is_valid)
            attempts.append(attempt_record)
            if is_valid:
                normalized_response = normalize_social_chat_response(
                    parsed_response,
                    fail_safe,
                    request_config=SOCIAL_CHAT_REQUEST_CONFIG,
                )
                attempt_record["normalized_response"] = normalized_response
                return normalized_response, {
                    "wrapped_prompt": wrapped_prompt,
                    "attempts": attempts,
                    "used_fail_safe": normalized_response == fail_safe,
                }
        except Exception as exc:
            attempt_record["raw_response"] = raw_response
            attempt_record["error"] = f"{type(exc).__name__}: {exc}"
            attempt_record["valid"] = False
            attempts.append(attempt_record)

    return fail_safe, {
        "wrapped_prompt": wrapped_prompt,
        "attempts": attempts,
        "used_fail_safe": True,
    }


def generate_mock_turn(speaker, listener, turn_index, context, max_turns):
    """Generate a deterministic mock turn for script verification."""
    topic = context["memory_keys"][0] if context["memory_keys"] else "最近的小镇消息"
    utterance = f"{speaker.scratch.first_name} 对 {listener.scratch.first_name} 说：我想到一件事，和“{topic}”有关。"
    return {
        "utterance": utterance,
        "end": turn_index >= max_turns - 1,
        "reasoning": "mock_responder",
    }


def simulate_chat(initiator, target, maze, max_turns=4, mock_respond=False):
    """Simulate a multi-turn social conversation using the current chat logic."""
    convo = []
    trace = []
    speaker = initiator
    listener = target

    for turn_index in range(max_turns):
        context = build_turn_context(speaker, listener, maze, convo)
        live_debug = None
        if mock_respond:
            decision = generate_mock_turn(speaker, listener, turn_index, context, max_turns)
        else:
            decision, live_debug = generate_live_turn(context["prompt"], turn_index)
        utterance = str(decision.get("utterance", "...")).strip()
        decision["utterance"] = utterance
        convo.append([speaker.name, utterance])
        trace.append(
            {
                "turn": turn_index,
                "speaker": speaker.name,
                "listener": listener.name,
                "memory_keys": context["memory_keys"],
                "dropped_memory_keys": context["dropped_memory_keys"],
                "speaker_context": context["speaker_context"],
                "history_text": context["history_text"],
                "prompt": context["prompt"],
                "decision": decision,
                "live_debug": live_debug,
            }
        )
        if decision.get("end", False):
            break
        speaker, listener = listener, speaker

    return convo, trace


def print_reference_chat(reference_chat):
    """Print the recorded transcript from the stored movement snapshot."""
    print("=== 参考日志对话 ===")
    if not reference_chat:
        print("(无参考对话记录)")
        return
    for index, row in enumerate(reference_chat, start=1):
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            print(f"{index:02d}. {row[0]}: {row[1]}")


def print_simulation_trace(convo, trace, maze_mode, show_prompt=False, show_raw=False):
    """Print the generated turn-by-turn simulation details."""
    print("\n=== 模拟生成过程 ===")
    print(f"maze_mode: {maze_mode}")
    for item in trace:
        print(f"\n[Turn {item['turn']}] {item['speaker']} -> {item['listener']}")
        print("memories:")
        if item["memory_keys"]:
            for memory in item["memory_keys"]:
                print(f"- {memory}")
        else:
            print("- none")
        if item.get("dropped_memory_keys"):
            print("dropped_memories:")
            for memory in item["dropped_memory_keys"]:
                print(f"- {memory}")
        if item.get("dropped_recent_events"):
            print("dropped_recent_events:")
            for event in item["dropped_recent_events"]:
                print(f"- {event}")
        print("utterance:")
        print(item["decision"].get("utterance", ""))
        print(f"end: {bool(item['decision'].get('end', False))}")
        live_debug = item.get("live_debug")
        if live_debug is not None:
            print(f"used_fail_safe: {live_debug.get('used_fail_safe', False)}")
            if show_prompt:
                print("wrapped_prompt:")
                print(live_debug.get("wrapped_prompt", ""))
            if show_raw:
                print("attempts:")
                for attempt in live_debug.get("attempts", []):
                    print(f"- attempt {attempt.get('attempt')}: valid={attempt.get('valid')}")
                    if "error" in attempt:
                        print(f"  error: {attempt['error']}")
                    if "raw_response" in attempt:
                        print("  raw_response:")
                        print(f"  {attempt['raw_response']}")
                    if "parsed_response" in attempt:
                        print("  parsed_response:")
                        print(f"  {attempt['parsed_response']}")
                    if "normalized_response" in attempt:
                        print("  normalized_response:")
                        print(f"  {attempt['normalized_response']}")
    print("\n=== 模拟生成对话 ===")
    for index, row in enumerate(convo, start=1):
        print(f"{index:02d}. {row[0]}: {row[1]}")


def build_argument_parser():
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(description="Replay and simulate an NPC chat from saved logs.")
    parser.add_argument(
        "--sim-path",
        default=str(ROOT / "environment" / "frontend_server" / "storage" / "sim_20260703_130547"),
        help="Simulation storage directory.",
    )
    parser.add_argument("--initiator", default="Klaus Mueller", help="Initiator persona name.")
    parser.add_argument("--target", default="Maria Lopez", help="Target persona name.")
    parser.add_argument("--step", type=int, default=None, help="Movement snapshot step to reference.")
    parser.add_argument("--max-turns", type=int, default=4, help="Maximum generated turns.")
    parser.add_argument(
        "--mock-respond",
        action="store_true",
        help="Use deterministic mock utterances instead of calling the live LLM.",
    )
    parser.add_argument(
        "--replay-only",
        action="store_true",
        help="Only print the reference chat stored in the movement snapshot.",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Print the wrapped prompt sent to the model for each turn.",
    )
    parser.add_argument(
        "--show-raw",
        action="store_true",
        help="Print raw model responses and parse results for each attempt.",
    )
    return parser


def main():
    """Run the CLI entry point."""
    parser = build_argument_parser()
    args = parser.parse_args()

    sim_path = Path(args.sim_path)
    meta = load_meta(sim_path)
    step, movement_snapshot = select_reference_step(sim_path, args.step)
    env_step, env_snapshot = select_environment_snapshot(sim_path, step)
    sim_time = parse_sim_time(movement_snapshot.get("meta", {}).get("curr_time") or meta.get("curr_time"))
    reference_chat = extract_reference_chat(movement_snapshot, args.initiator, args.target)

    print(f"sim_path: {sim_path}")
    print(f"reference_step: {step}")
    print(f"environment_step: {env_step}")
    print(f"sim_time: {sim_time}")
    print_reference_chat(reference_chat)

    if args.replay_only:
        return

    initiator = load_persona_from_sim(sim_path, args.initiator)
    target = load_persona_from_sim(sim_path, args.target)
    sync_persona_runtime_state(initiator, env_snapshot, sim_time, step)
    sync_persona_runtime_state(target, env_snapshot, sim_time, step)
    maze, maze_mode = build_maze(meta)

    convo, trace = simulate_chat(
        initiator=initiator,
        target=target,
        maze=maze,
        max_turns=args.max_turns,
        mock_respond=args.mock_respond,
    )
    print_simulation_trace(convo, trace, maze_mode, show_prompt=args.show_prompt, show_raw=args.show_raw)


if __name__ == "__main__":
    main()
