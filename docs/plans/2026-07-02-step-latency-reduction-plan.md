# Step Latency Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将高频 `20s+` 的 step 尾延迟压下来，同时保持 LLM 对 NPC 行为决策的主导权，不用硬编码接管行为。

**Architecture:** 先补齐 Ollama 侧可观测性，把慢请求拆成“输入过长 / 重试过多 / 调用过多 / 缓存未命中”四类；再把当前 `demand_thinking -> action_translation` 双阶段链路改造成“单次联合决策 + 失败回退”，并把大段自然语言上下文压缩成稳定的半结构化决策胶囊；最后在高频生理意图上引入语义状态指纹缓存，只复用同类状态下已验证可执行的 LLM 决策结果。

**Tech Stack:** Python, Ollama OpenAI-compatible API, JSONL debug logs, pytest, existing persona planning pipeline

---

## File Map

### Existing files to modify

- `g:\generative_agents\reverie\backend_server\persona\prompt_template\gpt_structure.py`
  - 统一 LLM 调用入口、缓存、时序日志写入；本计划在这里补充更细粒度的 Ollama 指标、请求标签和语义缓存命中日志。
- `g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py`
  - 现有 `run_gpt_prompt_demand_thinking()` 和 `run_gpt_prompt_action_translation()` 在这里；本计划会新增联合决策 Prompt 和决策胶囊构建器。
- `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py`
  - 现有 `decide_demand_action()` 在这里；本计划会在这里插入联合决策开关、回退路径、语义状态缓存命中和 A/B 标识。
- `g:\generative_agents\reverie\backend_server\persona\memory_structures\associative_memory.py`
  - 已有 dirty/checkpoint 逻辑；本计划只在需要时读取稳定经验摘要，不在这里增加新的决策逻辑。
- `g:\generative_agents\test\test_demand_thinking_memory_context.py`
  - 已有决策上下文相关测试；本计划会扩展到新的决策胶囊格式。
- `g:\generative_agents\test\test_action_translation_convergence.py`
  - 已有翻译收敛测试；本计划会补联合决策回退验证。

### New files to create

- `g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\joint_decision_v1.txt`
  - 单次联合决策 Prompt 模板，要求一次输出 `thought + action + target + detail + duration + reasoning`。
- `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\decision_state_cache.py`
  - 语义状态指纹缓存封装，负责 `build_state_signature() / get_cached_decision() / put_cached_decision()`。
- `g:\generative_agents\test\test_joint_decision_pipeline.py`
  - 覆盖联合决策成功、结构化失败回退、危急饥饿约束仍然成立。
- `g:\generative_agents\test\test_decision_state_cache.py`
  - 覆盖状态桶命中、跨桶失效、缓存结果必须是可执行动作。
- `g:\generative_agents\test\test_ollama_timing_metrics.py`
  - 覆盖 Ollama 时序日志提取器的字段完整性。
- `g:\generative_agents\test\check_step_latency_ab.py`
  - A/B 评估脚本，比较旧链路与新链路的 `p50/p95/max`。
- `g:\generative_agents\docs\llm_step_latency_optimization.md`
  - 记录最终方案、开关、指标口径和上线顺序。

---

### Task 1: 扩展 LLM 时序日志，先把慢请求拆清楚

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\persona\prompt_template\gpt_structure.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py`
- Test: `g:\generative_agents\test\test_ollama_timing_metrics.py`

- [ ] **Step 1: 写失败测试，固定 Ollama 指标提取格式**

```python
# g:\generative_agents\test\test_ollama_timing_metrics.py
from persona.prompt_template.gpt_structure import _extract_ollama_metrics


def test_extract_ollama_metrics_from_response_dict():
    response = {
        "total_duration": 12000000000,
        "load_duration": 300000000,
        "prompt_eval_duration": 1800000000,
        "eval_duration": 9900000000,
        "prompt_eval_count": 812,
        "eval_count": 98,
    }
    metrics = _extract_ollama_metrics(response)

    assert metrics["total_ms"] == 12000.0
    assert metrics["load_ms"] == 300.0
    assert metrics["prompt_eval_ms"] == 1800.0
    assert metrics["eval_ms"] == 9900.0
    assert metrics["prompt_eval_count"] == 812
    assert metrics["eval_count"] == 98
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```bash
pytest g:\generative_agents\test\test_ollama_timing_metrics.py -v
```

Expected:

```text
FAILED test_ollama_timing_metrics.py::test_extract_ollama_metrics_from_response_dict
```

- [ ] **Step 3: 在 `gpt_structure.py` 增加指标提取器和统一日志字段**

```python
# g:\generative_agents\reverie\backend_server\persona\prompt_template\gpt_structure.py
def _ns_to_ms(value):
  if value in (None, "", 0):
    return 0.0
  return round(float(value) / 1_000_000.0, 3)


def _extract_ollama_metrics(response):
  if not isinstance(response, dict):
    return {
      "total_ms": 0.0,
      "load_ms": 0.0,
      "prompt_eval_ms": 0.0,
      "eval_ms": 0.0,
      "prompt_eval_count": 0,
      "eval_count": 0,
    }
  return {
    "total_ms": _ns_to_ms(response.get("total_duration")),
    "load_ms": _ns_to_ms(response.get("load_duration")),
    "prompt_eval_ms": _ns_to_ms(response.get("prompt_eval_duration")),
    "eval_ms": _ns_to_ms(response.get("eval_duration")),
    "prompt_eval_count": int(response.get("prompt_eval_count") or 0),
    "eval_count": int(response.get("eval_count") or 0),
  }
```

- [ ] **Step 4: 给 `ChatGPT_request()` 和 `ChatGPT_safe_generate_response()` 打上 `prompt_kind`、重试次数和字符长度**

```python
# g:\generative_agents\reverie\backend_server\persona\prompt_template\gpt_structure.py
def ChatGPT_request(prompt, prompt_kind="generic", metadata=None):
  metadata = metadata or {}
  ...
  _log_llm_event(
    "chatgpt_request",
    {
      "caller": caller,
      "prompt_kind": prompt_kind,
      "prompt_hash": prompt_hash,
      "prompt_chars": len(prompt),
      "metadata": metadata,
      ...
    }
  )
```

```python
# g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py
output = ChatGPT_request(prompt, prompt_kind="demand_thinking")
```

- [ ] **Step 5: 运行测试，确认提取器通过**

Run:

```bash
pytest g:\generative_agents\test\test_ollama_timing_metrics.py -v
```

Expected:

```text
PASSED test_ollama_timing_metrics.py::test_extract_ollama_metrics_from_response_dict
```

- [ ] **Step 6: 提交**

```bash
git add g:\generative_agents\reverie\backend_server\persona\prompt_template\gpt_structure.py g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py g:\generative_agents\test\test_ollama_timing_metrics.py
git commit -m "perf(prompt): add fine-grained ollama timing metrics"
```

---

### Task 2: 用单次联合决策替代双次串行推理，并保留失败回退

**Files:**
- Create: `g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\joint_decision_v1.txt`
- Modify: `g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py`
- Test: `g:\generative_agents\test\test_joint_decision_pipeline.py`

- [ ] **Step 1: 写失败测试，要求联合决策返回完整字段**

```python
# g:\generative_agents\test\test_joint_decision_pipeline.py
def test_joint_decision_result_requires_thought_and_action_fields():
    result = {
        "thought": "I am hungry and should get food now.",
        "action": "Gather",
        "target": "refrigerator",
        "detail": "opening the refrigerator to gather food items",
        "duration": 10,
        "reasoning": "Hunger is the dominant need."
    }

    assert "thought" in result
    assert "action" in result
    assert "target" in result
    assert "detail" in result
    assert "duration" in result
```

- [ ] **Step 2: 新增联合决策模板**

```text
# g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\joint_decision_v1.txt
You are a decision engine for a sandbox simulation.

Identity:
!<INPUT 0>!

Decision Capsule:
!<INPUT 1>!

Task:
Choose the immediate next action only.
Return valid JSON with:
- thought
- action
- target
- detail
- duration
- reasoning
```

- [ ] **Step 3: 在 `run_gpt_prompt.py` 新增联合决策函数**

```python
# g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py
def run_gpt_prompt_joint_decision(persona, decision_capsule, verbose=False):
  prompt_input = [
    _compact_multiline_block(persona.scratch.get_str_iss(), max_lines=7, max_chars=900),
    decision_capsule,
  ]
  prompt_template = "persona/prompt_template/v2/joint_decision_v1.txt"
  prompt = generate_prompt(prompt_input, prompt_template)
  example_output = {
    "thought": "I am hungry and should gather food from the refrigerator now.",
    "action": "Gather",
    "target": "refrigerator",
    "detail": "opening the refrigerator to gather food items",
    "duration": 10,
    "reasoning": "Inventory is empty and hunger is urgent."
  }
  return ChatGPT_safe_generate_response(
    prompt,
    example_output,
    "Return only valid JSON with the required fields.",
    repeat=2,
    fail_safe_response={"action": "Idle", "target": "none", "detail": "idling", "duration": 10, "reasoning": "fail_safe", "thought": "I should pause briefly."},
    func_validate=lambda data, prompt=None: isinstance(data, dict) and all(k in data for k in ["thought", "action", "target", "detail", "duration", "reasoning"]),
    func_clean_up=lambda data, prompt=None: data,
    verbose=verbose,
  )
```

- [ ] **Step 4: 在 `plan.py` 增加联合决策开关和回退逻辑**

```python
# g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py
use_joint_decision = os.getenv("ENABLE_JOINT_DECISION_PIPELINE", "0") == "1"
if use_joint_decision:
  joint_result = run_gpt_prompt_joint_decision(persona, decision_capsule)
  if joint_result and joint_result.get("action"):
    thinking_text = str(joint_result.get("thought") or "").strip()
    decision = joint_result
  else:
    thinking_text = run_gpt_prompt_demand_thinking(...)
    decision = run_gpt_prompt_action_translation(...)
else:
  thinking_text = run_gpt_prompt_demand_thinking(...)
  decision = run_gpt_prompt_action_translation(...)
```

- [ ] **Step 5: 运行测试，确认联合决策路径和回退路径都通过**

Run:

```bash
pytest g:\generative_agents\test\test_joint_decision_pipeline.py g:\generative_agents\test\test_action_translation_convergence.py -v
```

Expected:

```text
PASSED test_joint_decision_pipeline.py::test_joint_decision_result_requires_thought_and_action_fields
PASSED test_action_translation_convergence.py::...
```

- [ ] **Step 6: 提交**

```bash
git add g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\joint_decision_v1.txt g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py g:\generative_agents\test\test_joint_decision_pipeline.py
git commit -m "perf(plan): add joint decision pipeline with fallback"
```

---

### Task 3: 把长文 Prompt 压成稳定的半结构化决策胶囊

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py`
- Modify: `g:\generative_agents\test\test_demand_thinking_memory_context.py`

- [ ] **Step 1: 写失败测试，固定决策胶囊必须包含四类核心信息**

```python
# g:\generative_agents\test\test_demand_thinking_memory_context.py
def test_decision_capsule_contains_status_rules_resources_and_memory():
    capsule = "\n".join([
        "Status: satiety=24 stamina=62 health=91 mood=55 inventory=empty",
        "Rules: satiety<30 and inventory_empty => Gather(valid_food_source)",
        "Resources: refrigerator, cafe counter, apple tree",
        "Experience: hunger -> standard food source reduces replanning",
    ])

    assert "Status:" in capsule
    assert "Rules:" in capsule
    assert "Resources:" in capsule
    assert "Experience:" in capsule
```

- [ ] **Step 2: 新增决策胶囊构建器**

```python
# g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py
def build_decision_capsule(persona, temporal_context, status_summary, rules, cooperative_context, nearby_resources, last_action_desc, intent_memory_summary, decision_convergence_hint):
  return "\n".join([
    f"Time: {_compact_multiline_block(temporal_context, max_lines=1, max_chars=120)}",
    f"Status: satiety={persona.scratch.satiety:.1f} stamina={persona.scratch.stamina:.1f} health={persona.scratch.health:.1f} mood={persona.scratch.mood:.1f} inventory={str(persona.scratch.inventory or 'empty')}",
    f"LastAction: {_collapse_text(last_action_desc) or 'None'}",
    f"Interpretation: {_compact_multiline_block(status_summary, max_lines=3, max_chars=240)}",
    f"Rules: {_compact_multiline_block(rules, max_lines=5, max_chars=320)}",
    f"Resources: {_compact_resource_context(nearby_resources, include_state=True, max_items=10)}",
    f"Cooperative: {_compact_multiline_block(cooperative_context, max_lines=3, max_chars=180)}",
    f"Experience: {_compact_multiline_block(intent_memory_summary, max_lines=4, max_chars=240)}",
    f"Convergence: {_compact_multiline_block(decision_convergence_hint, max_lines=2, max_chars=180)}",
  ])
```

- [ ] **Step 3: 让 `demand_thinking` 和 `joint_decision` 都优先使用胶囊**

```python
# g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py
decision_capsule = build_decision_capsule(
  persona,
  temporal_context,
  status_summary,
  physiological_rules,
  cooperative_context,
  object_states,
  last_action_desc,
  intent_memory_summary,
  translation_convergence_hint,
)
```

- [ ] **Step 4: 运行测试，确认胶囊格式稳定**

Run:

```bash
pytest g:\generative_agents\test\test_demand_thinking_memory_context.py -v
```

Expected:

```text
PASSED test_demand_thinking_memory_context.py::test_decision_capsule_contains_status_rules_resources_and_memory
```

- [ ] **Step 5: 提交**

```bash
git add g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py g:\generative_agents\test\test_demand_thinking_memory_context.py
git commit -m "perf(prompt): compress decision context into capsules"
```

---

### Task 4: 引入语义状态指纹缓存，只复用已验证可执行的决策

**Files:**
- Create: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\decision_state_cache.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py`
- Test: `g:\generative_agents\test\test_decision_state_cache.py`

- [ ] **Step 1: 写失败测试，固定状态桶命中规则**

```python
# g:\generative_agents\test\test_decision_state_cache.py
from persona.cognitive_modules.decision_state_cache import build_state_signature


def test_state_signature_changes_when_satiety_bucket_changes():
    sig_a = build_state_signature(
        persona_name="Klaus Mueller",
        intent_family="hunger",
        satiety=24.0,
        stamina=62.0,
        health=91.0,
        mood=55.0,
        inventory_state="empty",
        reachable_targets=["cafe counter", "refrigerator"],
        cooperative_state="none",
    )
    sig_b = build_state_signature(
        persona_name="Klaus Mueller",
        intent_family="hunger",
        satiety=41.0,
        stamina=62.0,
        health=91.0,
        mood=55.0,
        inventory_state="empty",
        reachable_targets=["cafe counter", "refrigerator"],
        cooperative_state="none",
    )

    assert sig_a != sig_b
```

- [ ] **Step 2: 新增状态指纹缓存模块**

```python
# g:\generative_agents\reverie\backend_server\persona\cognitive_modules\decision_state_cache.py
import hashlib
import json


def _bucket(value):
    value = float(value or 0.0)
    lower = int(value // 10) * 10
    upper = lower + 10
    return f"{lower}_{upper}"


def build_state_signature(**payload):
    normalized = {
        "persona_name": payload["persona_name"],
        "intent_family": payload["intent_family"],
        "satiety_bucket": _bucket(payload["satiety"]),
        "stamina_bucket": _bucket(payload["stamina"]),
        "health_bucket": _bucket(payload["health"]),
        "mood_bucket": _bucket(payload["mood"]),
        "inventory_state": payload["inventory_state"],
        "reachable_targets": sorted(payload["reachable_targets"]),
        "cooperative_state": payload["cooperative_state"],
    }
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

- [ ] **Step 3: 在 `plan.py` 只对高频意图启用缓存**

```python
# g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py
cacheable_intents = {"hunger", "rest", "recovery"}
if intent_family in cacheable_intents:
  state_signature = build_state_signature(
    persona_name=persona.name,
    intent_family=intent_family,
    satiety=persona.scratch.satiety,
    stamina=persona.scratch.stamina,
    health=persona.scratch.health,
    mood=persona.scratch.mood,
    inventory_state="empty" if not any(v > 0 for v in persona.scratch.inventory.values()) else "has_food",
    reachable_targets=gatherable_food_targets or [],
    cooperative_state="none" if "No special" in cooperative_context else "active",
  )
```

- [ ] **Step 4: 运行缓存测试**

Run:

```bash
pytest g:\generative_agents\test\test_decision_state_cache.py -v
```

Expected:

```text
PASSED test_decision_state_cache.py::test_state_signature_changes_when_satiety_bucket_changes
```

- [ ] **Step 5: 提交**

```bash
git add g:\generative_agents\reverie\backend_server\persona\cognitive_modules\decision_state_cache.py g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py g:\generative_agents\test\test_decision_state_cache.py
git commit -m "perf(cache): add semantic state cache for high-frequency decisions"
```

---

### Task 5: 做 A/B 基准和上线文档，验证是否真的压住尾延迟

**Files:**
- Create: `g:\generative_agents\test\check_step_latency_ab.py`
- Create: `g:\generative_agents\docs\llm_step_latency_optimization.md`

- [ ] **Step 1: 写对比脚本，汇总 `step_timing.jsonl` 和 `ollama_request_timing.jsonl`**

```python
# g:\generative_agents\test\check_step_latency_ab.py
import json
from pathlib import Path


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def summarize(values):
    values = sorted(values)
    if not values:
        return {"count": 0, "p50": 0, "p95": 0, "max": 0}
    return {
        "count": len(values),
        "p50": values[int(len(values) * 0.50)],
        "p95": values[min(len(values) - 1, int(len(values) * 0.95))],
        "max": values[-1],
    }
```

- [ ] **Step 2: 运行脚本，生成旧链路与新链路对比**

Run:

```bash
python g:\generative_agents\test\check_step_latency_ab.py
```

Expected:

```text
baseline_step_total_ms: {...}
optimized_step_total_ms: {...}
baseline_demand_thinking_ms: {...}
optimized_joint_decision_ms: {...}
```

- [ ] **Step 3: 写上线文档，固定验收标准**

```markdown
# LLM Step Latency Optimization

- Baseline commit: `660c59cf`
- Success criteria:
  - `step total p95` 下降至少 30%
  - `20s+` step 数量下降至少 50%
  - `joint decision fallback rate` 小于 10%
  - 高频饥饿决策缓存命中率大于 40%
```

- [ ] **Step 4: 提交**

```bash
git add g:\generative_agents\test\check_step_latency_ab.py g:\generative_agents\docs\llm_step_latency_optimization.md
git commit -m "docs(perf): add step latency benchmark and rollout guide"
```

---

## Rollout Order

1. 先做 Task 1，确认慢请求构成。
2. 再做 Task 2，把双次串行调用压成单次联合决策，并保留回退。
3. 然后做 Task 3，压缩 Prompt 到决策胶囊，降低输入成本和漂移。
4. 再做 Task 4，只对高频生理意图启用语义状态缓存。
5. 最后做 Task 5，用 A/B 脚本验证收益，再决定是否默认开启。

## Guardrails

- 不允许用硬编码规则直接替代 NPC 最终行为决策。
- 程序层只负责：
  - 物理约束
  - 结构校验
  - 回退兜底
  - 缓存复用
- 联合决策失败时必须能回退到当前 `demand_thinking -> action_translation` 老链路。
- 语义缓存只能复用“已经被程序校验为可执行”的结果。
- 所有新开关默认关闭，先做 A/B，再决定默认开启。

## Execution Handoff

Plan complete and saved to `docs/plans/2026-07-02-step-latency-reduction-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
