"""
Admin console handler for player-to-NPC control messages.

This channel is intentionally isolated from NPC social chat:
- no scratch.chat / last_chat writes
- no transcript logging
- no social dialogue logging
- no memory writes
- no stat changes
"""

import json

from persona.cognitive_modules.creator_chat_context import (
    build_creator_instruction_context,
    build_creator_notify_context,
    build_creator_query_context,
)
from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.prompt_template.gpt_structure import generate_prompt
from llm_api_config import get_task_route_request_config


_LLM_RUNNER = BaseSkillPack()
_LLM_RUNNER.name = "admin_console"
_ADMIN_REQUEST_CONFIG = get_task_route_request_config("general_chat")


def _normalize_conversation_history(conversation_history):
    if isinstance(conversation_history, str):
        try:
            conversation_history = json.loads(conversation_history)
        except Exception:
            return []
    if isinstance(conversation_history, list):
        return conversation_history[:12]
    return []


def _creator_like_fail_safe(message_mode, content):
    return {
        "reply": (
            "我记住了这条通知。"
            if message_mode == "notify"
            else "管理员指令已收到。"
            if message_mode == "instruction"
            else "我听到了你的提问。"
        ),
        "emoji": "🛠️",
        "next_action": content if message_mode == "instruction" else "",
        "reasoning": "Fallback admin console response",
    }


def _normalize_admin_instruction_text(content):
    normalized = str(content or "").strip()
    prefixes = (
        "请",
        "请你",
        "麻烦你",
        "帮我",
        "你现在",
        "请立即",
        "立刻",
        "马上",
        "去",
        "先",
    )
    for prefix in prefixes:
        if normalized.startswith(prefix) and len(normalized) > len(prefix):
            normalized = normalized[len(prefix):].strip()
            break
    return normalized or str(content or "").strip()


def _run_admin_llm(persona, maze, content, message_mode, conversation_history):
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

    def _validate(resp, prompt=""):
        try:
            data = resp if isinstance(resp, dict) else json.loads(resp)
            reply = str(data.get("reply", "")).strip()
            return bool(reply) and "next_action" in data
        except Exception:
            return False

    def _clean(resp, prompt=""):
        if isinstance(resp, dict):
            return resp
        return json.loads(resp)

    return _LLM_RUNNER.run_skill_llm_request(
        prompt,
        example_output='{"reply": "我现在正前往厨房。", "emoji": "🛠️", "next_action": "going to the kitchen", "reasoning": "Admin requested a status update"}',
        special_instruction="Provide valid JSON containing a non-empty reply, emoji, next_action, and reasoning.",
        repeat=3,
        fail_safe_response=_creator_like_fail_safe(message_mode, content),
        func_validate=_validate,
        func_clean_up=_clean,
        verbose=False,
        prompt_kind="admin_console",
        request_config=_ADMIN_REQUEST_CONFIG,
        skip_cache=True,
    )


def handle_admin_console_query(persona, maze, content, conversation_history=None):
    history = _normalize_conversation_history(conversation_history)
    decision = _run_admin_llm(persona, maze, content, "query", history)

    reply = str(decision.get("reply", "") or "").strip() or "我暂时没组织好回答，请再问我一次。"

    return {
        "ok": True,
        "status": "replied",
        "reply": reply,
        "message_mode": "query",
        "next_action": "",
        "applied": None,
    }


def handle_admin_console_notify(persona, content):
    note = str(content or "").strip()
    if note:
        reply = f"已收到通知：{note}"
    else:
        reply = "已收到通知。"
    return {
        "ok": True,
        "status": "replied",
        "reply": reply,
        "message_mode": "notify",
        "next_action": "",
        "applied": None,
    }


def handle_admin_console_instruction(persona, content):
    next_action = _normalize_admin_instruction_text(content)
    applied = None
    if getattr(persona.scratch, "set_admin_override_intent", None):
        persona.scratch.set_admin_override_intent(next_action, source="admin_console")
        applied = {
            "description": next_action,
            "mode": "replan_override",
        }
    if getattr(persona.scratch, "has_active_plan", None) and persona.scratch.has_active_plan():
        persona.scratch.interrupt_execution(
            "admin_console_override",
            payload={"next_action": next_action},
        )
    elif getattr(persona.scratch, "active_execution_state", None):
        persona.scratch.interrupt_execution(
            "admin_console_override",
            payload={"next_action": next_action},
        )
    if applied:
        reply = f"已收到管理员指令：{next_action}。{persona.name} 将重新规划并优先执行。"
    else:
        reply = "管理员指令已收到，但未能解析为可执行动作。"
    return {
        "ok": True,
        "status": "replied",
        "reply": reply,
        "message_mode": "instruction",
        "next_action": next_action,
        "applied": applied,
    }


def handle_admin_console_action(persona, maze, message_mode, content, conversation_history=None):
    normalized_mode = str(message_mode or "query").strip().lower()
    if normalized_mode == "instruction":
        return handle_admin_console_instruction(persona, content)
    if normalized_mode == "notify":
        return handle_admin_console_notify(persona, content)
    return handle_admin_console_query(persona, maze, content, conversation_history=conversation_history)
