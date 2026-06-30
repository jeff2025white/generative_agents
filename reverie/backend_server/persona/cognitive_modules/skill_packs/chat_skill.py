import json
import datetime
import sqlite3
import re
from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.prompt_template.gpt_structure import (
    generate_prompt,
    get_embedding
)
from persona.cognitive_modules.retrieve import new_retrieve

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

    def _update_pending_action(self, action_id, reply):
        db_path = "G:\\generative_agents\\environment\\frontend_server\\db.sqlite3"
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE translator_simpendingaction SET response = ?, processed = 1 WHERE id = ?",
                (reply, action_id)
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
            except Exception as e:
                print(f"Error parsing creator target in cognitive_decision: {e}")
                return {"mode": "creator", "reply": "I hear you, Creator.", "emoji": "👁️", "next_action": ""}

            # 1. Physical and physiological state
            curr_loc = persona.scratch.act_address if persona.scratch.act_address else "Unknown"
            curr_act = persona.scratch.act_description if persona.scratch.act_description else "Idle"
            phys_state = (
                f"- Satiety (饱腹度): {persona.scratch.satiety:.1f}/100.0\n"
                f"- Stamina (精力值): {persona.scratch.stamina:.1f}/100.0\n"
                f"- Current Location (当前物理位置): {curr_loc}\n"
                f"- Current Action (当前执行动作): {curr_act}"
            )

            # 2. Schedule and plans
            f_daily_schedule = persona.scratch.f_daily_schedule if persona.scratch.f_daily_schedule else []
            schedule_lines = []
            for act_name, duration in f_daily_schedule:
                schedule_lines.append(f"- {act_name} (for {duration} minutes)")
            schedule_str = "\n".join(schedule_lines)
            plans_str = f"Today's Schedule:\n{schedule_str}"

            # 3. Contextual memories queried dynamically by creator message
            focal_points = [content, persona.name]
            retrieved = new_retrieve(persona, focal_points, 5)
            all_mems = []
            for k, val in retrieved.items():
                for node in val:
                    all_mems.append(node.embedding_key)
            mems_str = "\n".join([f"- {m}" for m in list(set(all_mems))[:5]])
            
            if not mems_str:
                # Fallback to the latest 5 nodes from memory stream
                nodes_keys = list(persona.a_mem.id_to_node.keys())
                latest_keys = nodes_keys[-5:]
                latest_mems = [persona.a_mem.id_to_node[k].embedding_key for k in latest_keys]
                mems_str = "\n".join([f"- {m}" for m in latest_mems])

            # 4. Generate prompt V2
            prompt_input = [
                persona.scratch.get_str_iss(),
                content,
                action_type,
                phys_state,
                plans_str,
                mems_str,
                persona.name
            ]
            prompt = generate_prompt(prompt_input, "persona/prompt_template/v2/creator_comm_v2.txt")

            def cc_val(resp, prompt=""):
                try:
                    if isinstance(resp, dict):
                        return "reply" in resp
                    data = json.loads(resp)
                    return "reply" in data
                except:
                    return False

            def cc_clean(resp, prompt=""):
                if isinstance(resp, dict):
                    return resp
                return json.loads(resp)

            fail_safe = {
                "reply": "遵从您的指令，造物主。" if action_type == "instruction" else "我听到了您的声音，造物主。",
                "emoji": "👁️",
                "next_action": content if action_type == "instruction" else ""
            }

            decision = self.run_skill_llm_request(
                prompt,
                example_output='{"reply": "是的，造物主，我正前往寝室。", "emoji": "🫡", "next_action": "going to bed", "reasoning": "Awe towards creator"}',
                special_instruction="Provide valid JSON containing reply, emoji, and next_action.",
                repeat=3,
                fail_safe_response=fail_safe,
                func_validate=cc_val,
                func_clean_up=cc_clean,
                verbose=False
            )
            decision["mode"] = "creator"
            decision["action_id"] = action_id
            decision["content"] = content
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

            decision = self.run_skill_llm_request(
                prompt,
                example_output='{"monologue": "肚子有点饿了，等会儿去冰箱找点吃的吧。", "emoji": "💭"}',
                special_instruction="Provide valid JSON containing monologue and emoji.",
                repeat=3,
                fail_safe_response=fail_safe,
                func_validate=mono_val,
                func_clean_up=mono_clean,
                verbose=False
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
            
            convo = []
            speaker = persona
            listener = target_p
            
            # 4 turns of dialogue
            for turn in range(4):
                focal_points = [listener.name, "news", "rumor", "town"]
                retrieved = new_retrieve(speaker, focal_points, 10)
                mems = []
                for k, v in retrieved.items():
                    for node in v:
                        mems.append(node.embedding_key)
                mems_str = "\n".join([f"- {m}" for m in list(set(mems))[:5]])

                history_str = ""
                for s, u in convo:
                    history_str += f"{s}: {u}\n"

                # Inject social relationship graph constraints into context
                rel = speaker.a_mem.get_relationship(listener.name)
                rel_str = ""
                if rel:
                    rel_str = f" Relation status: {rel.get('relationship', 'acquaintance')} (Trust level: {rel.get('trust', 0.5):.2f})."
                    if rel.get("recent_events"):
                        rel_str += f" Recent interactions: {', '.join(rel['recent_events'])}."
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
                    try:
                        data = json.loads(resp)
                        return "utterance" in data and "end" in data
                    except:
                        return False

                def chat_clean(resp, prompt=""):
                    return json.loads(resp)

                fail_safe = {
                    "utterance": "你好！" if turn == 0 else "是的，我也这么觉得。",
                    "end": True if turn >= 3 else False
                }

                turn_decision = self.run_skill_llm_request(
                    prompt,
                    example_output='{"utterance": "你听说Isabella最近研发了新的咖啡吗？听说味道特别棒！", "end": false, "reasoning": "Spreading a nice rumor about Isabella"}',
                    special_instruction="Provide valid JSON containing utterance and end.",
                    repeat=3,
                    fail_safe_response=fail_safe,
                    func_validate=chat_val,
                    func_clean_up=chat_clean,
                    verbose=False
                )

                convo.append([speaker.name, turn_decision.get("utterance", "...")])
                if turn_decision.get("end", False):
                    break
                
                # Swap speaker and listener
                speaker, listener = listener, speaker

            return {
                "mode": "social",
                "convo": convo,
                "target_persona_name": target_p_name
            }

    def on_arrive(self, persona, target, maze, personas):
        # 0. Synchronization lock check:
        # If the interlocutor has already arrived and initiated the dialogue,
        # we copy their dialogue state and perform our own memory/physiological updates.
        if target and target.strip() in personas:
            target_p = personas[target.strip()]
            if target_p.scratch.chatting_with == persona.name and target_p.scratch.chat:
                print(f"=== [会话锁定/同步触发] {persona.name} 到达，接入 {target_p.name} 已经建立的会话 ===")
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
                persona.a_mem.add_event(
                    persona.scratch.curr_time, None,
                    persona.name, "chat with", target_p.name,
                    convo_summary, {"chat", persona.scratch.first_name, target_p.scratch.first_name}, 6,
                    (convo_summary, is_emb), None
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
                        persona.a_mem.add_event(
                            persona.scratch.curr_time, None,
                            target_p.name, "gossip to", persona.name,
                            g_cleaned, {"gossip", persona.scratch.first_name, target_p.scratch.first_name}, 5,
                            (g_cleaned, g_emb), None
                        )
                        print(f"=== [传闻与八卦结算] {persona.name} 记住了八卦: {g_cleaned} ===")
                except Exception as ge:
                    print(f"Warning: Gossip extraction failed: {ge}")

                # Update relationship graph for both parties in synchronization
                persona.a_mem.update_relationship(
                    target_p.name,
                    relation_type="friend" if persona.a_mem.get_relationship(target_p.name) is None else None,
                    trust_delta=0.05,
                    recent_event=convo_summary
                )
                target_p.a_mem.update_relationship(
                    persona.name,
                    relation_type="friend" if target_p.a_mem.get_relationship(persona.name) is None else None,
                    trust_delta=0.05,
                    recent_event=convo_summary
                )

                # Physiological recovery
                persona.scratch.stamina = min(100.0, persona.scratch.stamina + 15.0)
                print(f"=== [社交物理结算] {persona.name} 完成与 {target_p.name} 的对话同步结算，已更新双向关系图谱并恢复精力至 {persona.scratch.stamina:.1f} ===")
                return

        # Trigger LLM cognitive decision
        decision = self.cognitive_decision(persona, target, maze, personas)
        mode = decision.get("mode", "monologue")

        if mode == "creator":
            reply = decision.get("reply", "我听到了您的声音，造物主。")
            emoji = decision.get("emoji", "👁️")
            next_action = decision.get("next_action", "")
            action_id = decision.get("action_id")
            content = decision.get("content", "")

            # 1. Update database
            if action_id:
                self._update_pending_action(action_id, reply)

            # 2. Visual rendering
            persona.scratch.act_pronunciatio = emoji
            persona.scratch.act_description = f"responding to Creator: {reply}"

            # 3. Update chat history and last_chat state
            user_msg = content
            if content.startswith("User said: "):
                user_msg = content[len("User said: "):]
            persona.scratch.chat = [["User", user_msg], [persona.name, reply]]
            persona.scratch.chatting_with = "<creator>"
            persona.scratch.last_chat = reply

            # 3. Add to memory stream
            desc = f"{persona.name} received message from Creator and replied: '{reply}'"
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
            if next_action:
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

            # 1. Update both agents' states to chatting
            persona.scratch.chat = convo
            target_p.scratch.chat = convo
            persona.scratch.chatting_with = target_p_name
            target_p.scratch.chatting_with = persona.name
            persona.scratch.act_pronunciatio = "💬"
            target_p.scratch.act_pronunciatio = "💬"

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
            persona.a_mem.add_event(
                persona.scratch.curr_time, None,
                persona.name, "chat with", target_p.name,
                convo_summary, {"chat", persona.scratch.first_name, target_p.scratch.first_name}, 6,
                (convo_summary, is_emb), None
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
                    persona.a_mem.add_event(
                        persona.scratch.curr_time, None,
                        target_p.name, "gossip to", persona.name,
                        g_cleaned, {"gossip", persona.scratch.first_name, target_p.scratch.first_name}, 5,
                        (g_cleaned, g_emb), None
                    )
                    print(f"=== [传闻与八卦结算] {persona.name} 记住了八卦: {g_cleaned} ===")
            except Exception as ge:
                print(f"Warning: Gossip extraction failed: {ge}")

            # Update relationship graph for both parties
            persona.a_mem.update_relationship(
                target_p.name,
                relation_type="friend" if persona.a_mem.get_relationship(target_p.name) is None else None,
                trust_delta=0.05,
                recent_event=convo_summary
            )
            target_p.a_mem.update_relationship(
                persona.name,
                relation_type="friend" if target_p.a_mem.get_relationship(persona.name) is None else None,
                trust_delta=0.05,
                recent_event=convo_summary
            )

            # 4. Metabolic / physiological effect for the initiator
            persona.scratch.stamina = min(100.0, persona.scratch.stamina + 15.0)

            print(f"=== [社交物理结算] {persona.name} 发起与 {target_p_name} 的对话物理结算，已更新双向关系图谱并恢复精力至 {persona.scratch.stamina:.1f} ===")

