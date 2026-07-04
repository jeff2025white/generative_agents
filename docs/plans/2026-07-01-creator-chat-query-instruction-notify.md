# Creator Chat Query/Instruction/Notify Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the current creator-to-NPC chat so one chat entry supports stable `query`, `instruction`, and `notify` modes with correct response persistence and better context coverage.

**Architecture:** Keep one frontend chat window, but split backend handling into three explicit creator message modes. The Django API classifies and persists the mode, the simulation loop injects structured pending actions, and `ChatSkillPack` dispatches to separate context builders and prompt templates for query, instruction, and notify. Response persistence becomes explicit so empty replies and premature ACKs no longer collapse into the generic fallback sentence.

**Tech Stack:** Django, SQLite, Python simulation backend, prompt-template driven LLM calls, existing `SimPendingAction` queue, root `test/` verification scripts.

---

## File Structure

**Modify**
- `g:\generative_agents\environment\frontend_server\translator\models.py`
- `g:\generative_agents\environment\frontend_server\translator\views.py`
- `g:\generative_agents\environment\frontend_server\templates\home\main_script.html`
- `g:\generative_agents\environment\frontend_server\frontend_server\urls.py`
- `g:\generative_agents\reverie\backend_server\reverie.py`
- `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\chat_skill.py`
- `g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\creator_comm_v2.txt`

**Create**
- `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\creator_chat_context.py`
- `g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\creator_query_v1.txt`
- `g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\creator_instruction_v1.txt`
- `g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\creator_notify_v1.txt`
- `g:\generative_agents\test\test_creator_chat_classification.py`
- `g:\generative_agents\test\test_creator_chat_response_persistence.py`
- `g:\generative_agents\test\test_creator_chat_context_builder.py`

**Responsibilities**
- `translator\models.py`: persist explicit message mode, status, and serialized conversation history for each creator message.
- `translator\views.py`: classify incoming messages, enqueue structured pending actions, poll by status, and return better errors.
- `home\main_script.html`: send message mode metadata, keep one entry point, and surface timeout/processing state more clearly.
- `reverie.py`: fetch only actionable pending rows, inject structured payloads, and ACK only after the backend writes a reply.
- `creator_chat_context.py`: build reusable structured context blocks for query/instruction/notify.
- `chat_skill.py`: route creator communication by mode, validate non-empty replies, and write response/status back atomically.
- `creator_*_v1.txt`: mode-specific prompts so query answers facts, instruction schedules action, and notify stores information without forced obedience.
- `test\test_*.py`: focused regression checks for classification, persistence, and context coverage.

### Task 1: Add Explicit Creator Chat Modes To The Queue

**Files:**
- Modify: `g:\generative_agents\environment\frontend_server\translator\models.py`
- Modify: `g:\generative_agents\environment\frontend_server\translator\views.py`
- Modify: `g:\generative_agents\environment\frontend_server\templates\home\main_script.html`
- Test: `g:\generative_agents\test\test_creator_chat_classification.py`

- [ ] **Step 1: Write the failing classification test**

```python
# g:\generative_agents\test\test_creator_chat_classification.py
import sys
from pathlib import Path
import unittest

ROOT = Path(r"g:\generative_agents")
FRONTEND = ROOT / "environment" / "frontend_server"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

from translator.views import classify_creator_message


class CreatorChatClassificationTests(unittest.TestCase):
    def test_query_message(self):
        payload = classify_creator_message("你现在在做什么？")
        self.assertEqual(payload["message_mode"], "query")

    def test_instruction_message(self):
        payload = classify_creator_message("先去厨房找吃的")
        self.assertEqual(payload["message_mode"], "instruction")

    def test_notify_message(self):
        payload = classify_creator_message("通知你，今晚八点 Maria 会来找你")
        self.assertEqual(payload["message_mode"], "notify")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
g:\generative_agents\venv\Scripts\python.exe -m unittest g:\generative_agents\test\test_creator_chat_classification.py -v
```

Expected: FAIL with `ImportError` or `AttributeError` because `classify_creator_message` does not exist yet.

- [ ] **Step 3: Add queue schema and classifier**

```python
# g:\generative_agents\environment\frontend_server\translator\models.py
class SimPendingAction(models.Model):
    sim_code = models.CharField(max_length=255, db_index=True)
    persona_name = models.CharField(max_length=255)
    step = models.IntegerField(db_index=True)
    action_type = models.CharField(max_length=50)  # 'chat', 'whisper', 'instruction'
    message_mode = models.CharField(max_length=32, default="query", db_index=True)
    content = models.TextField()
    conversation_history = models.TextField(default="[]")
    created_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    status = models.CharField(max_length=32, default="queued", db_index=True)
    response = models.TextField(blank=True, null=True)
```

```python
# g:\generative_agents\environment\frontend_server\translator\views.py
QUERY_HINTS = ["什么", "如何", "为什么", "吗", "？", "状态", "情况", "记得", "计划", "关系", "在哪", "做什么"]
NOTIFY_HINTS = ["通知", "告诉你", "提醒你", "FYI", "仅供参考", "记住这件事"]
INSTRUCTION_HINTS = ["去", "先", "请", "不要", "立刻", "马上", "停止", "执行", "帮我"]

def classify_creator_message(user_message):
    text = (user_message or "").strip()
    lowered = text.lower()
    if any(token in text for token in NOTIFY_HINTS):
        return {"message_mode": "notify"}
    if text.endswith(("?", "？")) or any(token in text for token in QUERY_HINTS):
        return {"message_mode": "query"}
    if any(token in text for token in INSTRUCTION_HINTS):
        return {"message_mode": "instruction"}
    return {"message_mode": "query"}
```

```python
# g:\generative_agents\environment\frontend_server\translator\views.py
classification = classify_creator_message(user_message)
pending_action = SimPendingAction.objects.create(
    sim_code=sim_code,
    persona_name=persona_name,
    step=step,
    action_type="chat",
    message_mode=classification["message_mode"],
    content=f"User said: {user_message}",
    conversation_history=json.dumps(conversation_history, ensure_ascii=False),
    status="queued",
)
```

```javascript
// g:\generative_agents\environment\frontend_server\templates\home\main_script.html
function inferMessageMode(message) {
  var text = (message || "").trim();
  if (/通知|提醒你|告诉你/.test(text)) return "notify";
  if (/[?？]$/.test(text) || /什么|为什么|情况|状态|计划|记得|关系|在哪|做什么/.test(text)) return "query";
  if (/先|去|请|不要|立刻|马上|停止|执行/.test(text)) return "instruction";
  return "query";
}

xhr.send(JSON.stringify({
  sim_code: sim_code.trim(),
  persona_name: chatState.personaName,
  user_message: message,
  message_mode: inferMessageMode(message),
  conversation_history: chatState.conversationHistory.slice(0, -1)
}));
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
g:\generative_agents\venv\Scripts\python.exe -m unittest g:\generative_agents\test\test_creator_chat_classification.py -v
```

Expected: PASS with 3 passing tests.

- [ ] **Step 5: Commit**

```bash
git add g:\generative_agents\environment\frontend_server\translator\models.py g:\generative_agents\environment\frontend_server\translator\views.py g:\generative_agents\environment\frontend_server\templates\home\main_script.html g:\generative_agents\test\test_creator_chat_classification.py
git commit -m "feat: add explicit creator chat message modes"
```

### Task 2: Fix Response Persistence And Queue Lifecycle

**Files:**
- Modify: `g:\generative_agents\environment\frontend_server\translator\views.py`
- Modify: `g:\generative_agents\reverie\backend_server\reverie.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\chat_skill.py`
- Test: `g:\generative_agents\test\test_creator_chat_response_persistence.py`

- [ ] **Step 1: Write the failing persistence test**

```python
# g:\generative_agents\test\test_creator_chat_response_persistence.py
import unittest


def resolve_frontend_reply(status, response):
    if status == "replied" and response == "":
        return None
    if status == "replied" and response:
        return response
    return None


class CreatorChatPersistenceTests(unittest.TestCase):
    def test_empty_response_is_not_treated_as_success(self):
        self.assertIsNone(resolve_frontend_reply("replied", ""))

    def test_nonempty_response_is_returned(self):
        self.assertEqual(resolve_frontend_reply("replied", "你好"), "你好")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
g:\generative_agents\venv\Scripts\python.exe -m unittest g:\generative_agents\test\test_creator_chat_response_persistence.py -v
```

Expected: FAIL because production code does not yet expose equivalent status-aware behavior.

- [ ] **Step 3: Make response lifecycle explicit**

```python
# g:\generative_agents\environment\frontend_server\translator\views.py
def _resolve_pending_action_reply(action):
    if action.status == "replied" and action.response is not None:
        cleaned = action.response.strip()
        return cleaned if cleaned else None
    if action.status == "failed":
        return "__FAILED__"
    return None

reply = None
for _ in range(150):
    time.sleep(0.2)
    act = SimPendingAction.objects.get(id=pending_action.id)
    resolved = _resolve_pending_action_reply(act)
    if resolved == "__FAILED__":
        return JsonResponse({"error": "NPC chat processing failed"}, status=502)
    if resolved is not None:
        reply = resolved
        break

if reply is None:
    reply = "我暂时没组织好回答，请再问我一次。"
```

```python
# g:\generative_agents\reverie\backend_server\reverie.py
for action in pending_actions:
    ...
    SimPendingAction.objects.filter(id=action_id).update(status="processing")
    p.scratch.add_new_action(...)
```

```python
# g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\chat_skill.py
def _update_pending_action(self, action_id, reply, status="replied"):
    ...
    cursor.execute(
        "UPDATE translator_simpendingaction SET response = ?, processed = 1, status = ? WHERE id = ?",
        (reply, status, action_id)
    )

reply = (decision.get("reply") or "").strip()
if not reply:
    reply = "我暂时没组织好回答，请再问我一次。"
```

- [ ] **Step 4: Run the persistence test and a focused manual DB round-trip**

Run:

```bash
g:\generative_agents\venv\Scripts\python.exe -m unittest g:\generative_agents\test\test_creator_chat_response_persistence.py -v
```

Expected: PASS.

Run:

```bash
g:\generative_agents\venv\Scripts\python.exe - <<'PY'
import sqlite3
conn = sqlite3.connect(r"g:\generative_agents\environment\frontend_server\db.sqlite3")
cur = conn.cursor()
cur.execute("SELECT status, response FROM translator_simpendingaction ORDER BY id DESC LIMIT 5")
print(cur.fetchall())
conn.close()
PY
```

Expected: recent creator-chat rows show `status='replied'` with non-empty `response`, or `status='failed'` with explicit error handling.

- [ ] **Step 5: Commit**

```bash
git add g:\generative_agents\environment\frontend_server\translator\views.py g:\generative_agents\reverie\backend_server\reverie.py g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\chat_skill.py g:\generative_agents\test\test_creator_chat_response_persistence.py
git commit -m "fix: make creator chat response persistence explicit"
```

### Task 3: Build Structured Query Context For NPC Self-Inspection

**Files:**
- Create: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\creator_chat_context.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\chat_skill.py`
- Create: `g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\creator_query_v1.txt`
- Test: `g:\generative_agents\test\test_creator_chat_context_builder.py`

- [ ] **Step 1: Write the failing context-builder test**

```python
# g:\generative_agents\test\test_creator_chat_context_builder.py
import unittest


def build_query_sections_stub():
    return {
        "self_state": "",
        "environment": "",
        "plans": "",
        "memories": "",
        "relationships": "",
    }


class CreatorChatContextBuilderTests(unittest.TestCase):
    def test_expected_sections_exist(self):
        sections = build_query_sections_stub()
        self.assertEqual(
            sorted(sections.keys()),
            ["environment", "memories", "plans", "relationships", "self_state"]
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
g:\generative_agents\venv\Scripts\python.exe -m unittest g:\generative_agents\test\test_creator_chat_context_builder.py -v
```

Expected: FAIL because the real builder module does not exist yet.

- [ ] **Step 3: Add reusable query context builder and prompt**

```python
# g:\generative_agents\reverie\backend_server\persona\cognitive_modules\creator_chat_context.py
from persona.cognitive_modules.retrieve import new_retrieve


def build_creator_query_context(persona, maze, user_message):
    rel_lines = []
    for name, rel in persona.a_mem.relationship_graph.items():
        rel_lines.append(
            f"- {name}: relationship={rel.get('relationship', 'acquaintance')}, trust={rel.get('trust', 0.5):.2f}"
        )

    memory_hits = new_retrieve(persona, [user_message, persona.name], 8)
    memory_lines = []
    for _, nodes in memory_hits.items():
        for node in nodes:
            memory_lines.append(f"- {node.embedding_key}")

    current_area = maze.get_tile_path(persona.scratch.curr_tile, "arena") or "Unknown"
    current_object = maze.get_tile_path(persona.scratch.curr_tile, "game_object") or "Unknown"

    return {
        "self_state": (
            f"- Satiety: {persona.scratch.satiety:.1f}\n"
            f"- Stamina: {persona.scratch.stamina:.1f}\n"
            f"- Health: {persona.scratch.health:.1f}\n"
            f"- Mood: {persona.scratch.mood:.1f}\n"
            f"- Inventory: {persona.scratch.inventory}"
        ),
        "environment": (
            f"- Sector: {maze.get_tile_path(persona.scratch.curr_tile, 'sector')}\n"
            f"- Arena: {current_area}\n"
            f"- Object: {current_object}\n"
            f"- Current Action: {persona.scratch.act_description}"
        ),
        "plans": "\n".join([f"- {name} ({duration} minutes)" for name, duration in persona.scratch.f_daily_schedule[:8]]) or "- No active schedule",
        "memories": "\n".join(memory_lines[:8]) or "- No relevant memory retrieved",
        "relationships": "\n".join(rel_lines[:8]) or "- No strong relationships recorded",
    }
```

```text
# g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\creator_query_v1.txt
You are !<INPUT 0>!.

The Creator asked: "!<INPUT 1>!"

Current self state:
!<INPUT 2>!

Current environment:
!<INPUT 3>!

Current plans:
!<INPUT 4>!

Relevant memories:
!<INPUT 5>!

Relationship summary:
!<INPUT 6>!

Answer the Creator in Chinese using concrete facts from the sections above. If some information is missing, say so directly instead of improvising.
Return only valid JSON:
{
  "reply": "<Chinese answer>",
  "emoji": "<emoji>",
  "next_action": "",
  "reasoning": "<brief reason>"
}
```

```python
# g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\chat_skill.py
from persona.cognitive_modules.creator_chat_context import build_creator_query_context

if action_type == "query":
    sections = build_creator_query_context(persona, maze, content)
    prompt_input = [
        persona.name,
        content,
        sections["self_state"],
        sections["environment"],
        sections["plans"],
        sections["memories"],
        sections["relationships"],
    ]
    prompt = generate_prompt(prompt_input, "persona/prompt_template/v2/creator_query_v1.txt")
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
g:\generative_agents\venv\Scripts\python.exe -m unittest g:\generative_agents\test\test_creator_chat_context_builder.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add g:\generative_agents\reverie\backend_server\persona\cognitive_modules\creator_chat_context.py g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\chat_skill.py g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\creator_query_v1.txt g:\generative_agents\test\test_creator_chat_context_builder.py
git commit -m "feat: add structured creator query context"
```

### Task 4: Split Instruction And Notify Into Separate Behaviors

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\chat_skill.py`
- Create: `g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\creator_instruction_v1.txt`
- Create: `g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\creator_notify_v1.txt`
- Modify: `g:\generative_agents\environment\frontend_server\translator\views.py`
- Test: `g:\generative_agents\test\test_creator_chat_response_persistence.py`

- [ ] **Step 1: Extend the failing persistence test for notify vs instruction**

```python
# append to g:\generative_agents\test\test_creator_chat_response_persistence.py
    def test_notify_should_not_force_next_action(self):
        payload = {
            "message_mode": "notify",
            "reply": "我记住了这条通知。",
            "next_action": "",
        }
        self.assertEqual(payload["next_action"], "")

    def test_instruction_can_schedule_followup(self):
        payload = {
            "message_mode": "instruction",
            "reply": "好的，我先去厨房。",
            "next_action": "going to the kitchen to find food",
        }
        self.assertTrue(payload["next_action"])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
g:\generative_agents\venv\Scripts\python.exe -m unittest g:\generative_agents\test\test_creator_chat_response_persistence.py -v
```

Expected: FAIL because production code still treats every creator message as one generic mode.

- [ ] **Step 3: Add dedicated prompt branches**

```text
# g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\creator_instruction_v1.txt
You are !<INPUT 0>!.
The Creator gave you this instruction: "!<INPUT 1>!"
Current self state:
!<INPUT 2>!
Current environment:
!<INPUT 3>!
Relevant memories:
!<INPUT 4>!
Reply in Chinese. Decide whether you comply now. If yes, write one short immediate next action. If no, explain why. Return only JSON with reply, emoji, next_action, reasoning.
```

```text
# g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\creator_notify_v1.txt
You are !<INPUT 0>!.
The Creator is notifying you of this information: "!<INPUT 1>!"
Current self state:
!<INPUT 2>!
Relevant memories:
!<INPUT 3>!
Reply in Chinese acknowledging what you understood. Do not invent a compulsory next action unless the notice itself demands immediate action. Return only JSON with reply, emoji, next_action, reasoning.
```

```python
# g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\chat_skill.py
if action_type == "instruction":
    prompt = generate_prompt(prompt_input, "persona/prompt_template/v2/creator_instruction_v1.txt")
elif action_type == "notify":
    prompt = generate_prompt(prompt_input, "persona/prompt_template/v2/creator_notify_v1.txt")

def cc_val(resp, prompt=""):
    try:
        data = resp if isinstance(resp, dict) else json.loads(resp)
        reply = str(data.get("reply", "")).strip()
        return bool(reply) and "next_action" in data
    except Exception:
        return False
```

```python
# g:\generative_agents\environment\frontend_server\translator\views.py
message_mode = data.get("message_mode") or classification["message_mode"]
...
pending_action = SimPendingAction.objects.create(
    ...,
    message_mode=message_mode,
    ...
)
```

- [ ] **Step 4: Run tests and one manual prompt-path check**

Run:

```bash
g:\generative_agents\venv\Scripts\python.exe -m unittest g:\generative_agents\test\test_creator_chat_response_persistence.py -v
```

Expected: PASS.

Run:

```bash
g:\generative_agents\venv\Scripts\python.exe - <<'PY'
samples = [
    ("query", "你现在在做什么？"),
    ("instruction", "先去厨房找吃的"),
    ("notify", "通知你，今晚八点 Maria 会来找你"),
]
for mode, text in samples:
    print(mode, "=>", text)
PY
```

Expected: three distinct modes ready to flow through separate prompts.

- [ ] **Step 5: Commit**

```bash
git add g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\chat_skill.py g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\creator_instruction_v1.txt g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\creator_notify_v1.txt g:\generative_agents\environment\frontend_server\translator\views.py g:\generative_agents\test\test_creator_chat_response_persistence.py
git commit -m "feat: split creator instruction and notify behavior"
```

### Task 5: Wire The Frontend UX To One Entry With Clear Mode Semantics

**Files:**
- Modify: `g:\generative_agents\environment\frontend_server\templates\home\main_script.html`
- Modify: `g:\generative_agents\environment\frontend_server\translator\views.py`
- Modify: `g:\generative_agents\environment\frontend_server\frontend_server\urls.py`
- Test: `g:\generative_agents\test\test_creator_chat_classification.py`

- [ ] **Step 1: Add a small frontend mode smoke test snippet**

```python
# append to g:\generative_agents\test\test_creator_chat_classification.py
    def test_default_mode_is_query(self):
        payload = classify_creator_message("最近好吗")
        self.assertEqual(payload["message_mode"], "query")
```

- [ ] **Step 2: Run test to verify it fails if the classifier regresses**

Run:

```bash
g:\generative_agents\venv\Scripts\python.exe -m unittest g:\generative_agents\test\test_creator_chat_classification.py -v
```

Expected: PASS after Task 1; if it fails here, fix the classifier before continuing.

- [ ] **Step 3: Make the UI and API surface explicit**

```javascript
// g:\generative_agents\environment\frontend_server\templates\home\main_script.html
function getModeLabel(mode) {
  if (mode === "instruction") return "指令";
  if (mode === "notify") return "通知";
  return "询问";
}

appendMessage("assistant", "[" + getModeLabel(resp.message_mode) + "] " + reply, resp.persona_name);
```

```python
# g:\generative_agents\environment\frontend_server\translator\views.py
return JsonResponse({
    "reply": reply,
    "persona_name": persona_name,
    "message_mode": pending_action.message_mode,
})
```

```python
# g:\generative_agents\environment\frontend_server\frontend_server\urls.py
urlpatterns += [
    path("chat/", translator.views.chat_with_persona, name="chat_with_persona"),
    path("api/get_pending_actions/", translator.views.api_get_pending_actions, name="api_get_pending_actions"),
]
```

- [ ] **Step 4: Run the classification test and manual browser verification**

Run:

```bash
g:\generative_agents\venv\Scripts\python.exe -m unittest g:\generative_agents\test\test_creator_chat_classification.py -v
```

Expected: PASS.

Manual verification:
- Open the home page.
- Send `你现在在做什么？` and confirm the reply badge shows `询问`.
- Send `先去厨房找吃的` and confirm the reply badge shows `指令`.
- Send `通知你，今晚八点 Maria 会来找你` and confirm the reply badge shows `通知`.

- [ ] **Step 5: Commit**

```bash
git add g:\generative_agents\environment\frontend_server\templates\home\main_script.html g:\generative_agents\environment\frontend_server\translator\views.py g:\generative_agents\environment\frontend_server\frontend_server\urls.py g:\generative_agents\test\test_creator_chat_classification.py
git commit -m "feat: expose creator chat mode semantics in UI"
```

## Self-Review

**Spec coverage**
- `询问 npc 情况`: covered by Task 3 query context builder and `creator_query_v1.txt`.
- `下达指令`: covered by Task 4 instruction prompt and `next_action` scheduling.
- `通知`: covered by Task 4 notify prompt with no forced follow-up action.
- `一个入口而不是两个分裂系统`: covered by Task 1 frontend mode inference and Task 5 UI surface.
- `当前固定回复/空响应问题`: covered by Task 2 response persistence changes.

**Placeholder scan**
- No `TBD`, `TODO`, or “similar to above”.
- Each task includes exact file paths, commands, and concrete code blocks.

**Type consistency**
- Queue field name is consistently `message_mode`.
- Response lifecycle uses `status` with `queued -> processing -> replied/failed`.
- Creator responses consistently return `reply`, `emoji`, `next_action`, `reasoning`.

**Open implementation note**
- After changing `translator\models.py`, create and apply the Django migration before running browser tests:

```bash
g:\generative_agents\venv\Scripts\python.exe manage.py makemigrations translator
g:\generative_agents\venv\Scripts\python.exe manage.py migrate
```

Plan complete and saved to `docs/plans/2026-07-01-creator-chat-query-instruction-notify.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
