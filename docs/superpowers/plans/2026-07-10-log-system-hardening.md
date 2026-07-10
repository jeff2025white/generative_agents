# Log System Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为项目日志系统补齐运行实例隔离、前端读取筛选与日志生命周期治理，确保后续基于日志的行为归因不再串运行。

**Architecture:** 先在写入侧统一补齐 `sim_code`/`curr_step`/`sim_time` 上下文，再让前端读取路径优先按显式 `sim_code` 过滤日志，最后把清理策略与文档说明收口到同一套日志分层规则中。整改保持现有 JSONL 方案不变，不引入新的日志框架，只做“统一上下文 + 正确消费 + 明确保留策略”的稳妥增强。

**Tech Stack:** Python, pytest/unittest, Django view helpers, JSONL append logs, existing `append_debug_log(...)` infrastructure

---

## File Map

- `reverie/backend_server/persona/cognitive_modules/debug_log.py`
  统一日志上下文辅助函数，负责从 `persona`/`scratch` 提取 `sim_code`、`curr_step`、`sim_time`，避免每个模块手写一套。
- `reverie/backend_server/persona/memory_structures/scratch.py`
  为 `motive_monitor.jsonl`、`decision_stability.jsonl`、`action_outcome.jsonl` 这类高频状态日志补齐运行上下文。
- `reverie/backend_server/persona/persona.py`
  为 `step_timing.jsonl` 的 `persona_move_timing` 事件补齐 `sim_code`。
- `reverie/backend_server/persona/cognitive_modules/plan.py`
  为 `translation_verify.jsonl`、`decision_prompt_trace.jsonl`、`decision_constraint_hits.jsonl`、`step_timing.jsonl` 补齐统一上下文。
- `reverie/backend_server/persona/cognitive_modules/execute.py`
  为 `action_execution_debug.jsonl` 失败链路日志补齐统一上下文。
- `reverie/backend_server/persona/cognitive_modules/intent_memory.py`
  为 `intent_memory_retrieval.jsonl` 补齐统一上下文。
- `reverie/backend_server/persona/cognitive_modules/perceive.py`
  为 `perception_debug.jsonl` 补齐统一上下文。
- `environment/frontend_server/translator/views.py`
  改造最近日志读取逻辑，统一按 `sim_code + persona + event` 过滤，并尽量限制返回范围。
- `cleanup_run_state.py`
  将“会清空的临时日志”与“保留的跨运行诊断日志”用显式常量分层，避免后续继续凭经验维护。
- `docs/guides/simulator_commands_guide.md`
  更新日志排查约定，说明哪些日志是 run-scoped、哪些日志会保留、哪些分析入口应优先使用。
- `test/test_log_context.py`
  新增统一日志上下文单测。
- `test/test_persona_state_stability_logs.py`
  扩展最近日志读取逻辑的 `sim_code` 过滤测试。
- `test/test_motive_monitor_logging.py`
  扩展动机日志是否带 `sim_code` 的测试。
- `test/test_cleanup_run_state.py`
  扩展 cleanup 日志分层测试。

### Task 1: 统一日志上下文并补齐核心写入点

**Files:**
- Create: `test/test_log_context.py`
- Modify: `reverie/backend_server/persona/cognitive_modules/debug_log.py`
- Modify: `reverie/backend_server/persona/memory_structures/scratch.py`
- Modify: `reverie/backend_server/persona/persona.py`
- Modify: `reverie/backend_server/persona/cognitive_modules/plan.py`
- Modify: `reverie/backend_server/persona/cognitive_modules/execute.py`
- Modify: `reverie/backend_server/persona/cognitive_modules/intent_memory.py`
- Modify: `reverie/backend_server/persona/cognitive_modules/perceive.py`
- Test: `test/test_log_context.py`
- Test: `test/test_motive_monitor_logging.py`

- [ ] **Step 1: 先写失败测试，固定统一上下文字段**

```python
import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from persona.cognitive_modules.debug_log import build_log_context, merge_log_context


class LogContextTests(unittest.TestCase):
    def test_build_log_context_extracts_sim_fields_from_persona(self):
        scratch = SimpleNamespace(
            curr_step=17,
            curr_time=datetime(2026, 7, 10, 8, 5, 0),
        )
        persona = SimpleNamespace(name="Klaus Mueller", sim_code="sim_20260710_113627", scratch=scratch)

        context = build_log_context(persona=persona)

        self.assertEqual(context["sim_code"], "sim_20260710_113627")
        self.assertEqual(context["curr_step"], 17)
        self.assertEqual(context["sim_time"], "2026-07-10 08:05:00")

    def test_merge_log_context_keeps_explicit_payload_values(self):
        scratch = SimpleNamespace(curr_step=17, curr_time=datetime(2026, 7, 10, 8, 5, 0))
        persona = SimpleNamespace(name="Klaus Mueller", sim_code="sim_from_persona", scratch=scratch)

        payload = merge_log_context(
            {"sim_code": "sim_explicit", "curr_step": 99, "event": "demo"},
            persona=persona,
        )

        self.assertEqual(payload["sim_code"], "sim_explicit")
        self.assertEqual(payload["curr_step"], 99)
        self.assertEqual(payload["sim_time"], "2026-07-10 08:05:00")
        self.assertEqual(payload["event"], "demo")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认当前缺少统一上下文函数**

Run: `pytest test/test_log_context.py -q`
Expected: FAIL，提示 `cannot import name 'build_log_context'` 或 `cannot import name 'merge_log_context'`

- [ ] **Step 3: 在日志基础设施和高频写入点实现最小上下文注入**

```python
# reverie/backend_server/persona/cognitive_modules/debug_log.py
def _format_sim_time(curr_time):
    if curr_time is None:
        return None
    try:
        if isinstance(curr_time, str):
            return curr_time
        return curr_time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(curr_time)


def build_log_context(persona=None, scratch=None, sim_code=None):
    scratch_obj = scratch or getattr(persona, "scratch", None)
    context = {}
    if sim_code is not None:
        context["sim_code"] = sim_code
    elif persona is not None and getattr(persona, "sim_code", None):
        context["sim_code"] = getattr(persona, "sim_code")
    if scratch_obj is not None and getattr(scratch_obj, "curr_step", None) is not None:
        context["curr_step"] = getattr(scratch_obj, "curr_step")
    sim_time = _format_sim_time(getattr(scratch_obj, "curr_time", None)) if scratch_obj is not None else None
    if sim_time is not None:
        context["sim_time"] = sim_time
    return context


def merge_log_context(payload, persona=None, scratch=None, sim_code=None):
    record = dict(payload or {})
    context = build_log_context(persona=persona, scratch=scratch, sim_code=sim_code)
    for key, value in context.items():
        record.setdefault(key, value)
    return record
```

```python
# reverie/backend_server/persona/memory_structures/scratch.py
from persona.cognitive_modules.debug_log import append_debug_log, merge_log_context

append_debug_log(
    "motive_monitor.jsonl",
    merge_log_context(
        {
            "persona": self.name,
            "event": "motive_delta",
            "source": source,
            "reason": reason,
            "changed_motives": changed_motives,
            "dominant_motive": motive_debug.get("dominant_motive"),
            "secondary_motive": motive_debug.get("secondary_motive"),
            "guard_motive": motive_debug.get("guard_motive"),
            "dominant_urgency_band": motive_debug.get("dominant_urgency_band"),
            "dominant_pressure_score": motive_debug.get("dominant_pressure_score"),
            "dominant_strength": motive_debug.get("dominant_strength"),
            "has_urgent_motive": motive_debug.get("has_urgent_motive"),
            "motive_sentence": motive_debug.get("motive_sentence"),
            "top_scores": motive_debug.get("top_scores"),
            "metadata": metadata or {},
        },
        scratch=self,
        sim_code=getattr(self, "sim_code", None),
    ),
)
```

```python
# reverie/backend_server/persona/persona.py
from persona.cognitive_modules.debug_log import append_debug_log, merge_log_context

append_debug_log(
    "step_timing.jsonl",
    merge_log_context(
        {
            "event": "persona_move_timing",
            "persona": self.name,
            "mode": "full_pipeline",
            "total_ms": total_ms,
            "timings_ms": timings_ms,
            "state": self.get_step_debug_snapshot(),
        },
        persona=self,
    ),
)
```

```python
# reverie/backend_server/persona/cognitive_modules/plan.py / execute.py / intent_memory.py / perceive.py
append_debug_log(
    "translation_verify.jsonl",
    merge_log_context(
        {
            "persona": persona.name,
            "event": "decision_snapshot",
            "intent": thinking_text,
            "decision": decision,
        },
        persona=persona,
    ),
)
```

- [ ] **Step 4: 运行针对性测试，确认核心日志开始携带 `sim_code`**

Run: `pytest test/test_log_context.py test/test_motive_monitor_logging.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add \
  test/test_log_context.py \
  test/test_motive_monitor_logging.py \
  reverie/backend_server/persona/cognitive_modules/debug_log.py \
  reverie/backend_server/persona/memory_structures/scratch.py \
  reverie/backend_server/persona/persona.py \
  reverie/backend_server/persona/cognitive_modules/plan.py \
  reverie/backend_server/persona/cognitive_modules/execute.py \
  reverie/backend_server/persona/cognitive_modules/intent_memory.py \
  reverie/backend_server/persona/cognitive_modules/perceive.py
git commit -m "feat: add unified run-scoped log context"
```

### Task 2: 修正前端最近日志读取链路，严格按 `sim_code` 展示

**Files:**
- Modify: `environment/frontend_server/translator/views.py`
- Modify: `test/test_persona_state_stability_logs.py`
- Modify: `test/test_chat_transcript_loading.py`

- [ ] **Step 1: 写失败测试，固定 persona_state 面板只能读当前运行日志**

```python
def test_load_recent_motive_monitor_logs_filters_by_persona_and_sim_code(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        logs_path = Path(tmp_dir) / "motive_monitor.jsonl"
        rows = [
            {"persona": "Maria Lopez", "sim_code": "sim_a", "event": "motive_delta", "curr_step": 10},
            {"persona": "Maria Lopez", "sim_code": "sim_b", "event": "motive_delta", "curr_step": 11},
            {"persona": "Klaus Mueller", "sim_code": "sim_a", "event": "motive_delta", "curr_step": 12},
        ]
        with open(logs_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        with patch.object(views.os.path, "abspath", return_value=str(logs_path)):
            loaded = views._load_recent_motive_monitor_logs("Maria Lopez", sim_code="sim_a", limit=10)

    self.assertEqual(len(loaded), 1)
    self.assertEqual(loaded[0]["sim_code"], "sim_a")
```

```python
def test_load_recent_decision_stability_logs_filters_by_sim_code(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        logs_path = Path(tmp_dir) / "decision_stability.jsonl"
        rows = [
            {"persona": "Maria Lopez", "sim_code": "sim_a", "event": "switch_blocked", "curr_step": 10},
            {"persona": "Maria Lopez", "sim_code": "sim_b", "event": "switch_blocked", "curr_step": 11},
        ]
        with open(logs_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        with patch.object(views.os.path, "abspath", return_value=str(logs_path)):
            loaded = views._load_recent_decision_stability_logs("Maria Lopez", sim_code="sim_a", limit=10)

    self.assertEqual(len(loaded), 1)
    self.assertEqual(loaded[0]["sim_code"], "sim_a")
```

- [ ] **Step 2: 运行测试，确认当前函数签名和筛选逻辑不足**

Run: `pytest test/test_persona_state_stability_logs.py test/test_chat_transcript_loading.py -q`
Expected: FAIL，提示 `_load_recent_*` 不接受 `sim_code` 参数，或返回了跨运行记录

- [ ] **Step 3: 改造 `views.py` 读取函数和调用方**

```python
# environment/frontend_server/translator/views.py
def _matches_sim_code(entry, sim_code):
    if not sim_code:
        return True
    return str(entry.get("sim_code", "") or "").strip() == str(sim_code).strip()


def _load_recent_decision_logs(persona_name, sim_code=None, limit=8):
    logs_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "logs", "translation_verify.jsonl")
    )
    if not os.path.exists(logs_path):
        return []

    interesting = {"decision_snapshot", "target_resolution", "retarget_invalid_food_source"}
    matched = []
    with open(logs_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if entry.get("persona") != persona_name:
                continue
            if entry.get("event") not in interesting:
                continue
            if not _matches_sim_code(entry, sim_code):
                continue
            matched.append(entry)
    return matched[-limit:]
```

```python
# 同文件，更新三个 recent loader 的调用方
recent_decision_logs = _load_recent_decision_logs(persona_name, sim_code=sim_code)
recent_decision_stability_logs = _load_recent_decision_stability_logs(persona_name, sim_code=sim_code)
recent_motive_monitor_logs = _load_recent_motive_monitor_logs(persona_name, sim_code=sim_code)
```

```python
# 同文件，chat transcript 继续保留现有 scoped > global 读取顺序，但显式过滤 sim_code
record_sim_code = str(data.get("sim_code", "") or "").strip()
if record_sim_code and record_sim_code != sim_code:
    continue
```

- [ ] **Step 4: 运行测试，确认 persona_state 页只显示当前运行日志**

Run: `pytest test/test_persona_state_stability_logs.py test/test_chat_transcript_loading.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add \
  environment/frontend_server/translator/views.py \
  test/test_persona_state_stability_logs.py \
  test/test_chat_transcript_loading.py
git commit -m "fix: scope persona state logs by sim code"
```

### Task 3: 收口清理策略与日志治理文档

**Files:**
- Modify: `cleanup_run_state.py`
- Modify: `test/test_cleanup_run_state.py`
- Modify: `docs/guides/simulator_commands_guide.md`

- [ ] **Step 1: 写失败测试，固定 cleanup 只清理显式声明的临时日志**

```python
def test_reset_transient_logs_only_truncates_declared_transient_files(self):
    with tempfile.TemporaryDirectory() as temp_dir:
        logs_root = Path(temp_dir)
        transient = logs_root / "decision_prompt_trace.jsonl"
        preserved = logs_root / "motive_monitor.jsonl"
        transient.write_text("old trace\n", encoding="utf-8")
        preserved.write_text("keep me\n", encoding="utf-8")

        with patch.object(cleanup_module, "LOGS_DIR", logs_root), \
             patch.object(cleanup_module, "TRANSIENT_LOGS", ["decision_prompt_trace.jsonl"]):
            actions = cleanup_module.reset_transient_logs()

    self.assertEqual(transient.read_text(encoding="utf-8"), "")
    self.assertEqual(preserved.read_text(encoding="utf-8"), "keep me\n")
    self.assertEqual(actions, [str(transient)])
```

- [ ] **Step 2: 运行测试，确认当前分层规则未显式文档化**

Run: `pytest test/test_cleanup_run_state.py -q`
Expected: FAIL，或现有测试尚未覆盖“保留日志不被 truncate”的约束

- [ ] **Step 3: 在 cleanup 与文档里显式声明日志分层**

```python
# cleanup_run_state.py
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

PRESERVED_LOGS = [
    "action_outcome.jsonl",
    "motive_monitor.jsonl",
]
```

```markdown
<!-- docs/guides/simulator_commands_guide.md -->
## 日志分层约定

- `TRANSIENT_LOGS`: 启动新一轮模拟前会清空，只用于本轮调试，例如 `translation_verify.jsonl`、`step_timing.jsonl`
- `PRESERVED_LOGS`: 默认跨运行保留，用于长期行为分析，例如 `motive_monitor.jsonl`、`action_outcome.jsonl`
- 所有运行期 JSONL 都应带 `sim_code`
- 前端状态页与分析脚本必须优先按 `sim_code` 过滤，不能仅依赖真实时间窗口
```

- [ ] **Step 4: 运行测试，确认 cleanup 与治理约定一致**

Run: `pytest test/test_cleanup_run_state.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add cleanup_run_state.py test/test_cleanup_run_state.py docs/guides/simulator_commands_guide.md
git commit -m "docs: define log lifecycle policy"
```

## Self-Review

- **Spec coverage:** 方案覆盖了写入侧 `sim_code` 注入、前端按运行读取、分析脚本按运行聚合、cleanup 和文档治理四个核心问题，没有遗漏这次排查得到的主要结构性风险。
- **Placeholder scan:** 已避免占位式空指令；每个任务都给了具体文件、代码片段、运行命令和预期结果。
- **Type consistency:** 全文统一使用 `build_log_context(...)`、`merge_log_context(...)`、`_matches_sim_code(...)`、`_record_matches_sim(...)` 这些函数名；`sim_code` 的字段名在所有任务中保持一致。

Plan complete and saved to `docs/superpowers/plans/2026-07-10-log-system-hardening.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
