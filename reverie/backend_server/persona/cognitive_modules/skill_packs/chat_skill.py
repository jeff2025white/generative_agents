import json
import datetime
import sqlite3
import re
import random
from persona.cognitive_modules.action_command_utils import build_action_command
from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.prompt_template.gpt_structure import (
    ChatGPT_safe_generate_response,
    generate_prompt,
    get_embedding
)
from persona.cognitive_modules.retrieve import new_retrieve
from persona.cognitive_modules.creator_chat_context import (
    build_creator_query_context,
    build_creator_instruction_context,
    build_creator_notify_context,
)
from persona.cognitive_modules.social_dialogue_log import (
    inherit_social_dialogue_state,
    log_chat_transcript,
    log_social_dialogue,
    set_social_dialogue_state,
)
from llm_api_config import (
    get_default_social_chat_request_config,
    get_default_translation_request_config,
    get_task_route_request_config,
)


SOCIAL_CHAT_POLLUTION_MARKERS = (
    "interlocutor's name and traits",
    "retrieved memories/knowledge",
    "context of where/how you met",
    "previous lines of conversation",
    "speaker's first name",
    "iss01",
    "alex and jamie",
    "jamie's new project",
    "tech conference in vegas",
    "spontaneous downpour",
    "benefit alex's work",
)

SOCIAL_CHAT_REQUEST_CONFIG = get_default_social_chat_request_config()
SOCIAL_CHAT_TRANSLATION_REQUEST_CONFIG = get_default_translation_request_config()
GENERIC_SOCIAL_CHAT_UTTERANCES = {
    "是的，我也这么觉得。": True,
    "是的，我也这么认为。": True,
    "嗯，我也这么觉得。": True,
    "我同意。": True,
    "你好！": True,
    "...": True,
}


def _contains_cjk(text):
    """Return True when the text contains at least one CJK ideograph."""
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def is_polluted_social_chat_text(text):
    """Detect prompt-leak text and malformed self-chat artifacts."""
    normalized = str(text or "").strip()
    haystack = normalized.lower()
    if any(marker in haystack for marker in SOCIAL_CHAT_POLLUTION_MARKERS):
        return True
    return bool(re.search(r"(.+?) is having a conversation with \1\b", normalized, re.IGNORECASE))


def is_valid_social_chat_response(response):
    """Validate the social chat response structure and require Chinese output."""
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except Exception:
            return False
    if not is_structurally_valid_social_chat_response(response):
        return False
    utterance = str(response.get("utterance", "") or "").strip()
    return _contains_cjk(utterance)


def is_structurally_valid_social_chat_response(response):
    """Validate the minimal JSON structure for a social chat response."""
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except Exception:
            return False
    if not isinstance(response, dict):
        return False
    utterance = str(response.get("utterance", "") or "").strip()
    if not utterance:
        return False
    if "end" not in response:
        return False
    return True


def normalize_social_chat_response(response, fail_safe_response, request_config=None):
    """Ensure the final chat response is Chinese, translating when needed."""
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except Exception:
            return fail_safe_response
    if not is_structurally_valid_social_chat_response(response):
        return fail_safe_response
    if is_valid_social_chat_response(response):
        return response

    utterance = str(response.get("utterance", "") or "").strip()
    reasoning = str(response.get("reasoning", "") or "").strip()
    translation_prompt = (
        "将下面这段 NPC 对话输出改写为简体中文，并保持语气自然口语化。"
        "尽量简短，最好一句话，必要时最多两句短句。"
        "减少 AI 味和书面腔，不要像总结报告。"
        "可以带一点轻松幽默感，但不要刻意讲段子。"
        "只输出合法 JSON，包含 utterance、end、reasoning 三个字段。"
        "不要保留英文原句，不要输出 JSON 之外的任何内容。\n"
        f"utterance: {utterance}\n"
        f"end: {json.dumps(bool(response.get('end', False)))}\n"
        f"reasoning: {reasoning or 'translate to Chinese while keeping intent'}"
    )

    translated = ChatGPT_safe_generate_response(
        translation_prompt,
        '{"utterance": "哎，这事有点意思啊。", "end": false, "reasoning": "将原句改写成简短口语中文"}',
        "Return valid JSON only. The utterance must be brief colloquial Simplified Chinese with a light natural tone, never English.",
        repeat=2,
        fail_safe_response=fail_safe_response,
        func_validate=lambda resp, prompt="": is_valid_social_chat_response(resp),
        func_clean_up=lambda resp, prompt="": resp if isinstance(resp, dict) else json.loads(resp),
        verbose=False,
        prompt_kind="social_chat_translation",
        metadata={"llm_route": "default_social_chat_translation"},
        request_config=request_config or SOCIAL_CHAT_TRANSLATION_REQUEST_CONFIG,
    )
    return translated if is_valid_social_chat_response(translated) else fail_safe_response


def build_social_chat_fallback_utterance(turn, speaker, listener):
    """Return a short, varied fallback line so both roles do not collapse to one sentence."""
    pool_0 = [
        f"你好，{listener.scratch.first_name}，刚好碰见你。",
        f"哟，{listener.scratch.first_name}，今天在忙什么呢？",
        f"嘿，{listener.scratch.first_name}，好久没见你了！",
        f"{listener.scratch.first_name}，你也在这附近转悠啊？",
    ]
    pool_1 = [
        "我刚路过这边，顺便和你打个招呼。",
        "最近镇上有什么新鲜事吗？",
        "我正好有空，就过来溜达溜达。",
        "我也是出来透透气，没想到碰到你。",
    ]
    pool_2 = [
        "我也是这么想的，不过还得再看看。",
        "说的也是，回头有空一起聊聊。",
        "嗯，我回去琢磨琢磨。",
        "好的好的，有消息再跟你说。",
    ]
    pool_3 = [
        "那我先去忙了，回头再聊。",
        "行，那咱们改天再约。",
        "好嘞，先撤了，拜拜。",
        "走了走了，下次见。",
    ]
    pools = [pool_0, pool_1, pool_2, pool_3]
    idx = min(turn, 3)
    return random.choice(pools[idx])


def sanitize_social_chat_utterance(raw_utterance, turn, speaker, listener, convo):
    """Replace empty or repetitive filler lines with a more specific fallback."""
    utterance = str(raw_utterance or "").strip()
    previous_utterance = ""
    if convo:
        previous_utterance = str(convo[-1][1] or "").strip()
    if not utterance:
        return build_social_chat_fallback_utterance(turn, speaker, listener)
    if utterance == previous_utterance:
        return build_social_chat_fallback_utterance(turn, speaker, listener)
    if utterance in GENERIC_SOCIAL_CHAT_UTTERANCES and any(
        str(existing_utterance or "").strip() == utterance for _, existing_utterance in convo
    ):
        return build_social_chat_fallback_utterance(turn, speaker, listener)
    return utterance


def _is_polluted_social_memory(node):
    """Detect prompt-leak chat memories and known contaminated summary traces."""
    description = str(getattr(node, "description", "") or "")
    embedding_key = str(getattr(node, "embedding_key", "") or "")
    return is_polluted_social_chat_text(f"{description}\n{embedding_key}")


def filter_social_chat_memory_nodes(nodes):
    """Drop known polluted memories before building the chat prompt."""
    filtered = []
    dropped = []
    for node in nodes or []:
        if _is_polluted_social_memory(node):
            dropped.append(str(getattr(node, "embedding_key", "") or getattr(node, "description", "") or ""))
            continue
        filtered.append(node)
    return filtered, dropped


def collect_social_chat_memory_keys(retrieved):
    """Collect deduplicated memory strings for the chat prompt."""
    seen = set()
    kept = []
    dropped = []
    for nodes in (retrieved or {}).values():
        filtered_nodes, dropped_nodes = filter_social_chat_memory_nodes(nodes)
        dropped.extend(dropped_nodes)
        for node in filtered_nodes:
            key = str(getattr(node, "embedding_key", "") or getattr(node, "description", "") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            kept.append(key)
    return kept[:5], dropped


def filter_social_chat_recent_events(events):
    """Remove polluted relationship summary strings before prompt assembly."""
    kept = []
    dropped = []
    seen = set()
    for event in events or []:
        text = str(event or "").strip()
        if not text:
            continue
        if is_polluted_social_chat_text(text):
            dropped.append(text)
            continue
        if text in seen:
            continue
        seen.add(text)
        kept.append(text)
    return kept, dropped


class ChatSkillPack(BaseSkillPack):



    def __init__(self):
        super().__init__()
        self.name = "chat"
        self.associated_xp = "socializing"

    def can_execute(self, persona, target, maze) -> bool:
        # Preconditions are always physically satisfied for monologues & creator comms.
        # For social chat, target is another persona name, they must be in the same sector/arena.
        if target and not target.startswith("<creator>") and target not in ["none", ""]:
            # Check if target is a known persona nearby
            target_p_name = target.strip()
            # If target_p_name contains a persona name, we allow it.
            # Spatial proximity is handled by the path finder.
            return True
        return True

    def get_target_tiles(self, persona, target, maze) -> list:
        # Monologues and Creator Comms happen in place.
        # Social chats happen adjacent to the target persona.
        return [persona.scratch.curr_tile]

    def _update_pending_action(self, action_id, reply, status="replied"):
        db_path = "G:\\generative_agents\\environment\\frontend_server\\db.sqlite3"
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE translator_simpendingaction SET response = ?, processed = 1, status = ? WHERE id = ?",
                (reply, status, action_id)
            )
            conn.commit()
            conn.close()
            print(f"=== [造物主沟通物理结算] 数据库状态已成功更新 (ID: {action_id}) ===")
        except Exception as e:
            print(f"Warning: Failed to update SimPendingAction DB: {e}")

    def cognitive_decision(self, persona, target, maze, personas) -> dict:
        act_address = persona.scratch.act_address if persona.scratch.act_address else ""
        
        # ----------------------------------------------------
        # MODE C: Creator/Observer Communication
        # ----------------------------------------------------
        if "<creator>" in act_address:
            try:
                json_part = act_address.split("<creator>")[-1].strip()
                action_data = json.loads(json_part)
                action_id = action_data["id"]
                action_type = action_data["action_type"]
                content = action_data["content"]
                message_mode = action_data.get("message_mode") or ("instruction" if action_type == "instruction" else "query")
                conversation_history = action_data.get("conversation_history", [])
                if isinstance(conversation_history, str):
                    try:
                        conversation_history = json.loads(conversation_history)
                    except Exception:
                        conversation_history = []
            except Exception as e:
                print(f"Error parsing creator target in cognitive_decision: {e}")
                return {"mode": "creator", "reply": "我听到了你的声音，创造者。", "emoji": "👁️", "next_action": ""}

            if message_mode == "instruction":
                sections = build_creator_instruction_context(persona, maze, content, conversation_history)
                prompt_input = [
                    persona.name,
                    content,
                    sections["self_state"],
                    sections["environment"],
                    sections["memories"],
                    sections["history"],
                ]
                prompt = generate_prompt(prompt_input, "persona/prompt_template/v2/creator_instruction_v1.txt")
            elif message_mode == "notify":
                sections = build_creator_notify_context(persona, maze, content, conversation_history)
                prompt_input = [
                    persona.name,
                    content,
                    sections["self_state"],
                    sections["memories"],
                    sections["history"],
                ]
                prompt = generate_prompt(prompt_input, "persona/prompt_template/v2/creator_notify_v1.txt")
            else:
                sections = build_creator_query_context(persona, maze, content, conversation_history)
                prompt_input = [
                    persona.name,
                    content,
                    sections["self_state"],
                    sections["environment"],
                    sections["plans"],
                    sections["memories"],
                    sections["relationships"],
                    sections["history"],
                ]
                prompt = generate_prompt(prompt_input, "persona/prompt_template/v2/creator_query_v1.txt")

            def cc_val(resp, prompt=""):
                try:
                    data = resp if isinstance(resp, dict) else json.loads(resp)
                    reply = str(data.get("reply", "")).strip()
                    return bool(reply) and "next_action" in data
                except Exception:
                    return False

            def cc_clean(resp, prompt=""):
                if isinstance(resp, dict):
                    return resp
                return json.loads(resp)

            fail_safe = {
                "reply": (
                    "我记住了这条通知。"
                    if message_mode == "notify"
                    else "遵从您的指令，造物主。"
                    if message_mode == "instruction"
                    else "我听到了你的提问，创造者。"
                ),
                "emoji": "👁️",
                "next_action": content if message_mode == "instruction" else "",
                "reasoning": "Fallback creator communication response",
            }
            creator_request_config = get_task_route_request_config("general_chat")

            decision = self.run_skill_llm_request(
                prompt,
                example_output='{"reply": "是的，造物主，我正前往寝室。", "emoji": "🫡", "next_action": "going to bed", "reasoning": "Awe towards creator"}',
                special_instruction="Provide valid JSON containing a non-empty reply, emoji, next_action, and reasoning.",
                repeat=3,
                fail_safe_response=fail_safe,
                func_validate=cc_val,
                func_clean_up=cc_clean,
                verbose=False,
                request_config=creator_request_config,
            )
            decision["mode"] = "creator"
            decision["action_id"] = action_id
            decision["content"] = content
            decision["message_mode"] = message_mode
            return decision

        # ----------------------------------------------------
        # MODE A: Inner Monologue (Self-Talk)
        # ----------------------------------------------------
        elif not target or target == "none" or target == "":
            focal_points = [persona.name]
            retrieved = new_retrieve(persona, focal_points, 5)
            all_mems = []
            for k, val in retrieved.items():
                for node in val:
                    all_mems.append(node.embedding_key)
            mems_str = "\n".join([f"- {m}" for m in list(set(all_mems))[:5]])

            phys_state = (
                f"- Satiety: {persona.scratch.satiety:.1f}/100.0\n"
                f"- Stamina: {persona.scratch.stamina:.1f}/100.0\n"
                f"- Health: {persona.scratch.health:.1f}/100.0\n"
                f"- Inventory: {str(persona.scratch.inventory)}"
            )

            prompt_input = [
                persona.scratch.get_str_iss(),
                phys_state,
                persona.scratch.act_description,
                mems_str,
                persona.name
            ]
            prompt = generate_prompt(prompt_input, "persona/prompt_template/v2/monologue_v1.txt")

            def mono_val(resp, prompt=""):
                try:
                    data = json.loads(resp)
                    return "monologue" in data and "emoji" in data
                except:
                    return False

            def mono_clean(resp, prompt=""):
                return json.loads(resp)

            fail_safe = {
                "monologue": "今天还有很多事情要做，继续加油吧。",
                "emoji": "💭"
            }
            monologue_request_config = get_task_route_request_config("general_chat")

            decision = self.run_skill_llm_request(
                prompt,
                example_output='{"monologue": "肚子有点饿了，等会儿去冰箱找点吃的吧。", "emoji": "💭"}',
                special_instruction="Provide valid JSON containing monologue and emoji.",
                repeat=3,
                fail_safe_response=fail_safe,
                func_validate=mono_val,
                func_clean_up=mono_clean,
                verbose=False,
                request_config=monologue_request_config,
            )
            decision["mode"] = "monologue"
            return decision

        # ----------------------------------------------------
        # MODE B: Social Conversation (Gossip)
        # ----------------------------------------------------
        else:
            # We will generate a multi-turn conversation and rumor propagation
            target_p_name = target.strip()
            if target_p_name not in personas:
                return {"mode": "monologue", "monologue": "一个人自言自语中...", "emoji": "💭"}

            target_p = personas[target_p_name]
            curr_context = f"{persona.name} and {target_p.name} met in the {maze.get_tile_path(persona.scratch.curr_tile, 'arena')}."
            log_social_dialogue(
                persona,
                "generation",
                "social_generation_started",
                target_name=target_p_name,
                payload={
                    "arena_context": curr_context,
                },
            )
            
            convo = []
            speaker = persona
            listener = target_p
            
            # 4 turns of dialogue
            for turn in range(4):
                focal_points = [listener.name, "news", "rumor", "town"]
                retrieved = new_retrieve(speaker, focal_points, 10)
                memory_keys, dropped_memory_keys = collect_social_chat_memory_keys(retrieved)
                mems_str = "\n".join([f"- {m}" for m in memory_keys]) if memory_keys else "- none"

                history_str = ""
                for s, u in convo:
                    history_str += f"{s}: {u}\n"

                # Inject social relationship graph constraints into context
                rel = speaker.a_mem.get_relationship(listener.name)
                rel_str = ""
                dropped_recent_events = []
                if rel:
                    rel_str = f" Relation status: {rel.get('relationship', 'acquaintance')} (Trust level: {rel.get('trust', 0.5):.2f})."
                    recent_events, dropped_recent_events = filter_social_chat_recent_events(
                        rel.get("recent_events", [])
                    )
                    if recent_events:
                        rel_str += f" Recent interactions: {', '.join(recent_events)}."
                speaker_context = f"{curr_context}{rel_str}"

                prompt_input = [
                    speaker.scratch.get_str_iss(),
                    listener.name,
                    mems_str,
                    speaker_context,
                    history_str if history_str else "No conversation started yet.",
                    speaker.scratch.first_name
                ]
                prompt = generate_prompt(prompt_input, "persona/prompt_template/v2/social_chat_gossip_v1.txt")

                def chat_val(resp, prompt=""):
                    _ = prompt
                    return is_structurally_valid_social_chat_response(resp)

                def chat_clean(resp, prompt=""):
                    _ = prompt
                    parsed = resp if isinstance(resp, dict) else json.loads(resp)
                    return normalize_social_chat_response(
                        parsed,
                        fail_safe,
                        request_config=SOCIAL_CHAT_REQUEST_CONFIG,
                    )

                fail_safe = {
                    "utterance": "你好！" if turn == 0 else "是的，我也这么觉得。",
                    "end": True if turn >= 3 else False
                }

                turn_decision = self.run_skill_llm_request(
                    prompt,
                    example_output='{"utterance": "你听说没，Isabella新出的咖啡好像挺火。", "end": false, "reasoning": "用简短口语化的方式开启话题"}',
                    special_instruction="Provide valid JSON containing utterance and end. The utterance must be brief colloquial Simplified Chinese, ideally one short sentence and at most two short sentences, with low AI tone and a light natural humor when appropriate, never English.",
                    repeat=3,
                    fail_safe_response=fail_safe,
                    func_validate=chat_val,
                    func_clean_up=chat_clean,
                    verbose=False,
                    prompt_kind="social_chat_generation",
                    metadata={"llm_route": "default_social_chat"},
                    request_config=SOCIAL_CHAT_REQUEST_CONFIG,
                    skip_cache=True,
                )

                final_utterance = sanitize_social_chat_utterance(
                    turn_decision.get("utterance", "..."),
                    turn,
                    speaker,
                    listener,
                    convo,
                )
                turn_decision["utterance"] = final_utterance
                log_social_dialogue(
                    persona,
                    "generation",
                    "social_generation_turn",
                    target_name=target_p_name,
                    payload={
                        "turn": turn,
                        "speaker": speaker.name,
                        "listener": listener.name,
                        "memory_keys": memory_keys,
                        "dropped_memory_keys": dropped_memory_keys,
                        "dropped_recent_events": dropped_recent_events,
                        "utterance": final_utterance,
                        "end": bool(turn_decision.get("end", False)),
                    },
                )
                convo.append([speaker.name, final_utterance])
                if turn_decision.get("end", False):
                    break
                
                # Swap speaker and listener
                speaker, listener = listener, speaker

            log_social_dialogue(
                persona,
                "generation",
                "social_generation_finished",
                target_name=target_p_name,
                payload={
                    "turn_count": len(convo),
                    "ended_by_model": bool(turn_decision.get("end", False)) if convo else False,
                },
            )
            return {
                "mode": "social",
                "convo": convo,
                "target_persona_name": target_p_name
            }

    def on_arrive(self, persona, target, maze, personas):
        log_social_dialogue(
            persona,
            "arrival",
            "on_arrive_enter",
            target_name=target.strip() if isinstance(target, str) else target,
            payload={
                "act_address": persona.scratch.act_address,
                "act_description": persona.scratch.act_description,
            },
        )
        # 0. Synchronization lock check:
        # If the interlocutor has already arrived and initiated the dialogue,
        # we copy their dialogue state and perform our own memory/physiological updates.
        if target and target.strip() in personas:
            target_p = personas[target.strip()]
            if target_p.scratch.chatting_with == persona.name and target_p.scratch.chat:
                print(f"=== [会话锁定/同步触发] {persona.name} 到达，接入 {target_p.name} 已经建立的会话 ===")
                inherited_dialogue_id = inherit_social_dialogue_state(persona, target_p, role="target")
                log_social_dialogue(
                    persona,
                    "arrival",
                    "conversation_lock_hit",
                    target_name=target_p.name,
                    dialogue_id=inherited_dialogue_id,
                    payload={
                        "source_persona": target_p.name,
                        "shared_turn_count": len(target_p.scratch.chat or []),
                    },
                )
                convo = target_p.scratch.chat
                
                # Update own state
                persona.scratch.chat = convo
                persona.scratch.chatting_with = target_p.name
                persona.scratch.act_pronunciatio = "💬"

                # Update last_chat for both
                p_last = None
                t_last = None
                for speaker, utterance in reversed(convo):
                    if speaker == persona.name and p_last is None:
                        p_last = utterance
                    if speaker == target_p.name and t_last is None:
                        t_last = utterance
                if p_last is not None:
                    persona.scratch.last_chat = p_last
                if t_last is not None:
                    target_p.scratch.last_chat = t_last
                
                # Summarize conversation from own perspective
                convo_summary = f"{persona.name} and {target_p.name} talked about recent topics and shared town gossip."
                try:
                    from persona.prompt_template.run_gpt_prompt import run_gpt_prompt_summarize_conversation
                    convo_summary = run_gpt_prompt_summarize_conversation(persona, convo)[0]
                except Exception as e:
                    print(f"Warning: Failed to call run_gpt_prompt_summarize_conversation: {e}")

                is_emb = get_embedding(convo_summary)
                summary_node = persona.a_mem.add_event(
                    persona.scratch.curr_time, None,
                    persona.name, "chat with", target_p.name,
                    convo_summary, {"chat", persona.scratch.first_name, target_p.scratch.first_name}, 6,
                    (convo_summary, is_emb), None
                )
                log_social_dialogue(
                    persona,
                    "memory",
                    "summary_written",
                    target_name=target_p.name,
                    payload={
                        "summary_node_id": getattr(summary_node, "node_id", None),
                        "mode": "sync_copy",
                    },
                )

                # Gossip extraction for persona
                try:
                    convo_text = "\n".join([f"{s}: {u}" for s, u in convo])
                    gossip_prompt = (
                        f"You are {persona.name}. You just had this conversation with {target_p.name}:\n"
                        f"\"\"\"\n{convo_text}\n\"\"\"\n\n"
                        f"What did you learn or hear about other townspeople or events? Summarize it in Chinese as a single statement. "
                        f"If you learned nothing or it was just general chatter, return 'none'."
                    )
                    from persona.prompt_template.gpt_structure import ChatGPT_single_request
                    gossip_learned = ChatGPT_single_request(gossip_prompt).strip()
                    if "error" not in gossip_learned.lower() and gossip_learned.lower() != "none" and gossip_learned.strip():
                        gossip_cleaned = gossip_learned.replace('"', '').replace("'", "").strip()
                        g_emb = get_embedding(g_cleaned := f"{persona.name} heard that {gossip_cleaned}")
                        gossip_node = persona.a_mem.add_event(
                            persona.scratch.curr_time, None,
                            target_p.name, "gossip to", persona.name,
                            g_cleaned, {"gossip", persona.scratch.first_name, target_p.scratch.first_name}, 5,
                            (g_cleaned, g_emb), None
                        )
                        log_social_dialogue(
                            persona,
                            "memory",
                            "gossip_written",
                            target_name=target_p.name,
                            payload={
                                "gossip_node_id": getattr(gossip_node, "node_id", None),
                                "mode": "sync_copy",
                            },
                        )
                        print(f"=== [传闻与八卦结算] {persona.name} 记住了八卦: {g_cleaned} ===")
                except Exception as ge:
                    print(f"Warning: Gossip extraction failed: {ge}")

                # Update relationship graph for both parties in synchronization
                persona.a_mem.update_relationship(
                    target_p.name,
                    relation_type="friend" if persona.a_mem.get_relationship(target_p.name) is None else None,
                    trust_delta=0.02,
                    recent_event=convo_summary
                )
                target_p.a_mem.update_relationship(
                    persona.name,
                    relation_type="friend" if target_p.a_mem.get_relationship(persona.name) is None else None,
                    trust_delta=0.02,
                    recent_event=convo_summary
                )
                log_social_dialogue(
                    persona,
                    "settlement",
                    "relationship_updated",
                    target_name=target_p.name,
                    payload={
                        "trust_delta": 0.02,
                        "mode": "sync_copy",
                    },
                )

                # Physiological recovery
                persona.scratch.stamina = min(100.0, persona.scratch.stamina + 4.0)
                persona.scratch.mood = min(100.0, persona.scratch.mood + 3.0)
                log_social_dialogue(
                    persona,
                    "settlement",
                    "dialogue_completed",
                    target_name=target_p.name,
                    payload={
                        "result": "sync_copy_completed",
                        "stamina": persona.scratch.stamina,
                    },
                )
                print(f"=== [社交物理结算] {persona.name} 完成与 {target_p.name} 的对话同步结算，已更新双向关系图谱并恢复精力至 {persona.scratch.stamina:.1f} ===")
                return

        if target and target.strip() in personas:
            log_social_dialogue(
                persona,
                "arrival",
                "conversation_lock_miss",
                target_name=target.strip(),
                payload={"reason": "target_has_no_ready_chat"},
            )

        # Trigger LLM cognitive decision
        decision = self.cognitive_decision(persona, target, maze, personas)
        mode = decision.get("mode", "monologue")

        if mode == "creator":
            reply = str(decision.get("reply", "") or "").strip()
            if not reply:
                reply = "我暂时没组织好回答，请再问我一次。"
            emoji = decision.get("emoji", "👁️")
            next_action = str(decision.get("next_action", "") or "").strip()
            action_id = decision.get("action_id")
            content = decision.get("content", "")
            message_mode = decision.get("message_mode", "query")

            # 1. Update database
            if action_id:
                self._update_pending_action(action_id, reply)

            # 2. Visual rendering
            persona.scratch.act_pronunciatio = emoji
            persona.scratch.act_description = "communicating with the Creator"

            # 3. Update chat history and last_chat state
            user_msg = content
            if content.startswith("User said: "):
                user_msg = content[len("User said: "):]
            persona.scratch.chat = [["User", user_msg], [persona.name, reply]]
            persona.scratch.chatting_with = "<creator>"
            persona.scratch.last_chat = reply
            log_chat_transcript(
                persona,
                persona.scratch.chat,
                target_name="creator",
                channel="creator",
                payload={
                    "message_mode": message_mode,
                    "action_id": action_id,
                },
            )

            # 3. Add to memory stream
            desc = f"{persona.name} handled creator {message_mode}: '{user_msg}' -> '{reply}'"
            is_emb = get_embedding(desc)
            persona.a_mem.add_event(
                persona.scratch.curr_time, None,
                "Creator", "message to", persona.name,
                desc, {"Creator", "message", persona.name.split()[0]}, 10,
                (desc, is_emb), None
            )

            # 4. Metabolic and physiological effect
            # Interaction with creator gives emotional stability / comfort
            persona.scratch.stamina = min(100.0, persona.scratch.stamina + 20.0)

            # 5. Handle compliance task scheduling
            if message_mode == "instruction" and next_action:
                # Find target object (heuristic mapping)
                target_obj = "bed"
                if any(kw in next_action.lower() for kw in ["cook", "stove", "kitchen", "meal"]):
                    target_obj = "stove"
                elif any(kw in next_action.lower() for kw in ["eat", "food", "apple", "fridge", "refrigerator"]):
                    target_obj = "refrigerator"
                elif any(kw in next_action.lower() for kw in ["sleep", "bed", "rest", "tired"]):
                    target_obj = "bed"
                elif any(kw in next_action.lower() for kw in ["study", "desk", "library", "read", "write"]):
                    target_obj = "desk"
                elif any(kw in next_action.lower() for kw in ["cafe", "coffee", "counter"]):
                    target_obj = "coffee maker"

                address = persona.s_mem.find_nearest_object(target_obj)
                if not address:
                    address = persona.scratch.living_area

                # Add compliant action immediately
                persona.scratch.add_new_action(
                    address,
                    30,
                    next_action,
                    "🫡",
                    (persona.name, "execute", target_obj),
                    build_action_command(None, target_obj, source="chat_followup", raw_action="execute"),
                    None,
                    None,
                    {},
                    None,
                    None,
                    None,
                    (None, None, None),
                    persona.scratch.curr_time
                )
                persona.scratch.planned_path = []
                persona.scratch.act_path_set = False

        elif mode == "monologue":
            monologue = decision.get("monologue", "自言自语中...")
            emoji = decision.get("emoji", "💭")

            # 1. Visual rendering
            persona.scratch.act_pronunciatio = emoji
            persona.scratch.act_description = monologue

            # 2. Add monologue thought to memory stream
            desc = f"{persona.name} had an inner monologue: '{monologue}'"
            is_emb = get_embedding(desc)
            persona.a_mem.add_event(
                persona.scratch.curr_time, None,
                persona.name, "think", "none",
                desc, {"think", "monologue", persona.scratch.first_name}, 4,
                (desc, is_emb), None
            )

            # 3. Emotional comfort restoring Stamina
            persona.scratch.stamina = min(100.0, persona.scratch.stamina + 8.0)
            print(f"=== [内心独白物理结算] {persona.name} 进行独白: {monologue}，恢复精力至 {persona.scratch.stamina:.1f} ===")

        elif mode == "social":
            convo = decision.get("convo", [])
            target_p_name = decision.get("target_persona_name")
            target_p = personas[target_p_name]
            if getattr(persona.scratch, "social_dialogue_id", None):
                set_social_dialogue_state(target_p, persona.scratch.social_dialogue_id, partner_name=persona.name, role="target")

            # 1. Update both agents' states to chatting
            persona.scratch.chat = convo
            target_p.scratch.chat = convo
            persona.scratch.chatting_with = target_p_name
            target_p.scratch.chatting_with = persona.name
            persona.scratch.act_pronunciatio = "💬"
            target_p.scratch.act_pronunciatio = "💬"
            log_chat_transcript(
                persona,
                convo,
                target_name=target_p_name,
                dialogue_id=getattr(persona.scratch, "social_dialogue_id", None),
                channel="social",
                payload={
                    "participants": [persona.name, target_p.name],
                },
            )
            log_social_dialogue(
                persona,
                "settlement",
                "shared_conversation_written",
                target_name=target_p_name,
                payload={
                    "turn_count": len(convo),
                },
            )

            # Update last_chat for both
            p_last = None
            t_last = None
            for speaker, utterance in reversed(convo):
                if speaker == persona.name and p_last is None:
                    p_last = utterance
                if speaker == target_p.name and t_last is None:
                    t_last = utterance
            if p_last is not None:
                persona.scratch.last_chat = p_last
            if t_last is not None:
                target_p.scratch.last_chat = t_last

            # 2. Generate conversation summary & write to memory only for the initiator
            convo_summary = f"{persona.name} and {target_p.name} talked about recent topics and shared town gossip."
            try:
                from persona.prompt_template.run_gpt_prompt import run_gpt_prompt_summarize_conversation
                convo_summary = run_gpt_prompt_summarize_conversation(persona, convo)[0]
            except Exception as e:
                print(f"Warning: Failed to call run_gpt_prompt_summarize_conversation: {e}")

            is_emb = get_embedding(convo_summary)
            summary_node = persona.a_mem.add_event(
                persona.scratch.curr_time, None,
                persona.name, "chat with", target_p.name,
                convo_summary, {"chat", persona.scratch.first_name, target_p.scratch.first_name}, 6,
                (convo_summary, is_emb), None
            )
            log_social_dialogue(
                persona,
                "memory",
                "summary_written",
                target_name=target_p_name,
                payload={
                    "summary_node_id": getattr(summary_node, "node_id", None),
                    "mode": "generated",
                },
            )

            # 3. Gossip / Rumor Propagation
            try:
                convo_text = "\n".join([f"{s}: {u}" for s, u in convo])
                gossip_prompt = (
                    f"You are {persona.name}. You just had this conversation with {target_p.name}:\n"
                    f"\"\"\"\n{convo_text}\n\"\"\"\n\n"
                    f"What did you learn or hear about other townspeople or events? Summarize it in Chinese as a single statement. "
                    f"If you learned nothing or it was just general chatter, return 'none'."
                )
                from persona.prompt_template.gpt_structure import ChatGPT_single_request
                gossip_learned = ChatGPT_single_request(gossip_prompt).strip()
                if "error" not in gossip_learned.lower() and gossip_learned.lower() != "none" and gossip_learned.strip():
                    gossip_cleaned = gossip_learned.replace('"', '').replace("'", "").strip()
                    g_emb = get_embedding(g_cleaned := f"{persona.name} heard that {gossip_cleaned}")
                    gossip_node = persona.a_mem.add_event(
                        persona.scratch.curr_time, None,
                        target_p.name, "gossip to", persona.name,
                        g_cleaned, {"gossip", persona.scratch.first_name, target_p.scratch.first_name}, 5,
                        (g_cleaned, g_emb), None
                    )
                    log_social_dialogue(
                        persona,
                        "memory",
                        "gossip_written",
                        target_name=target_p_name,
                        payload={
                            "gossip_node_id": getattr(gossip_node, "node_id", None),
                            "mode": "generated",
                        },
                    )
                    print(f"=== [传闻与八卦结算] {persona.name} 记住了八卦: {g_cleaned} ===")
            except Exception as ge:
                print(f"Warning: Gossip extraction failed: {ge}")

            # Update relationship graph for both parties
            persona.a_mem.update_relationship(
                target_p.name,
                relation_type="friend" if persona.a_mem.get_relationship(target_p.name) is None else None,
                    trust_delta=0.02,
                recent_event=convo_summary
            )
            target_p.a_mem.update_relationship(
                persona.name,
                relation_type="friend" if target_p.a_mem.get_relationship(persona.name) is None else None,
                    trust_delta=0.02,
                recent_event=convo_summary
            )
            log_social_dialogue(
                persona,
                "settlement",
                "relationship_updated",
                target_name=target_p_name,
                payload={
                    "trust_delta": 0.02,
                    "mode": "generated",
                },
            )

            # 4. Metabolic / physiological effect for the initiator
            persona.scratch.stamina = min(100.0, persona.scratch.stamina + 4.0)
            persona.scratch.mood = min(100.0, persona.scratch.mood + 3.0)
            log_social_dialogue(
                persona,
                "settlement",
                "dialogue_completed",
                target_name=target_p_name,
                payload={
                    "result": "generated_completed",
                    "turn_count": len(convo),
                    "stamina": persona.scratch.stamina,
                    "mood": persona.scratch.mood,
                },
            )

            print(f"=== [社交物理结算] {persona.name} 发起与 {target_p_name} 的对话物理结算，已更新双向关系图谱并恢复精力至 {persona.scratch.stamina:.1f} ===")
