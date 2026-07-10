# Experience-Priority Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让重复成功/失败自动沉淀为“强经验”，并在阶段1、阶段2、解析层中把强经验放到比普通记忆更高的优先级，从而自然避免同一空实例的无限重试。

**Architecture:** 在 `ActionOutcomeRecord` 之上新增一层运行时“经验归纳视图”，把实例级失败、实例级成功和策略级 fallback 归并为结构化经验单元。阶段1不再只展示松散记忆摘要，而是注入 `StrongAvoidExperience` / `StrongPreferExperience` / `ExperienceGuidance`；阶段2接收 `ExperienceGuard` 约束；解析层按经验强度而不是简单最近失败列表来排序候选地址。

**Tech Stack:** Python, pytest/unittest, `Scratch` 运行时状态, `append_debug_log` JSONL 日志, 现有 `ActionOutcomeRecord`/prompt compiler/target resolver

---

### Task 1: 经验归纳视图与运行时存储

**Files:**
- Modify: `reverie/backend_server/persona/memory_structures/scratch.py`
- Modify: `reverie/backend_server/persona/cognitive_modules/action_outcomes.py`
- Test: `test/test_action_outcomes.py`
- Test: `test/test_scratch_legacy_load.py`

- [ ] **Step 1: 先写失败测试，固定经验单元的数据形状**

```python
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from persona.memory_structures.scratch import Scratch


def test_record_action_outcome_builds_instance_avoid_experience():
    scratch = Scratch("Isabella Rodriguez")
    scratch.curr_step = 16
    outcome = {
        "persona": "Isabella Rodriguez",
        "curr_step": 16,
        "action": {
            "skill_id": "gather",
            "target": "refrigerator",
            "target_address": "the Ville:Hobbs Cafe:cafe:refrigerator",
            "intent_family": "restore_satiety",
        },
        "execution": {
            "result": "failed",
            "reason": "resource_empty",
            "reason_class": "resource_state",
        },
        "effects": {"progress_score": 0.0},
    }

    scratch.record_action_outcome(outcome)
    units = scratch.get_experience_priority_units(intent_family="restore_satiety")

    assert units[0]["experience_kind"] == "avoid"
    assert units[0]["resource_scope"] == "instance"
    assert units[0]["resource_instance_key"] == "the ville:hobbs cafe:cafe:refrigerator"
    assert units[0]["recommendation"] == "avoid_this_instance"


def test_record_action_outcome_builds_instance_prefer_experience():
    scratch = Scratch("Maria Lopez")
    scratch.curr_step = 117
    outcome = {
        "persona": "Maria Lopez",
        "curr_step": 117,
        "action": {
            "skill_id": "consume",
            "target": "apple",
            "target_address": "the Ville:Johnson Park:park:apple tree",
            "intent_family": "restore_satiety",
        },
        "execution": {"result": "success", "reason": None, "reason_class": "other"},
        "effects": {"progress_score": 0.95},
    }

    scratch.record_action_outcome(outcome)
    units = scratch.get_experience_priority_units(intent_family="restore_satiety")

    assert units[0]["experience_kind"] == "prefer"
    assert units[0]["resource_instance_key"] == "the ville:johnson park:park:apple tree"
    assert units[0]["recommendation"] == "prefer_this_instance"
```

- [ ] **Step 2: 运行测试，确认当前缺少经验归纳接口**

Run: `pytest test/test_action_outcomes.py test/test_scratch_legacy_load.py -q`
Expected: FAIL，提示 `Scratch` 缺少 `get_experience_priority_units` 或经验单元字段不存在

- [ ] **Step 3: 在 `Scratch` 中加入经验归纳视图，但不要引入显式“第 N 次失败”阈值**

```python
def _normalize_experience_unit(self, outcome):
    action = outcome.get("action") or {}
    execution = outcome.get("execution") or {}
    effects = outcome.get("effects") or {}
    reason = str(execution.get("reason") or "").strip().lower()
    result = str(execution.get("result") or "").strip().lower()
    progress_score = float(effects.get("progress_score", 0.0) or 0.0)
    instance_key = str(action.get("target_address") or "").strip().lower()

    if reason == "resource_empty" and instance_key:
        return {
            "experience_kind": "avoid",
            "intent_family": action.get("intent_family"),
            "skill_id": action.get("skill_id"),
            "resource_scope": "instance",
            "resource_instance_key": instance_key,
            "resource_type": action.get("target"),
            "recommendation": "avoid_this_instance",
            "confidence": 0.72,
            "freshness_step": outcome.get("curr_step"),
            "evidence_summary": f"{action.get('target')} at {action.get('target_address')} was empty recently.",
            "supporting_outcome_ids": [outcome.get("outcome_id")],
        }
    if result == "success" and instance_key and progress_score >= 0.6:
        return {
            "experience_kind": "prefer",
            "intent_family": action.get("intent_family"),
            "skill_id": action.get("skill_id"),
            "resource_scope": "instance",
            "resource_instance_key": instance_key,
            "resource_type": action.get("target"),
            "recommendation": "prefer_this_instance",
            "confidence": min(1.0, 0.45 + progress_score * 0.5),
            "freshness_step": outcome.get("curr_step"),
            "evidence_summary": f"{action.get('target')} at {action.get('target_address')} worked well recently.",
            "supporting_outcome_ids": [outcome.get("outcome_id")],
        }
    return None


def _merge_experience_unit(self, unit):
    self.experience_priority_units = list(getattr(self, "experience_priority_units", []) or [])
    for existing in self.experience_priority_units:
        same_key = (
            existing.get("experience_kind") == unit.get("experience_kind")
            and existing.get("intent_family") == unit.get("intent_family")
            and existing.get("resource_instance_key") == unit.get("resource_instance_key")
            and existing.get("recommendation") == unit.get("recommendation")
        )
        if not same_key:
            continue
        existing["confidence"] = min(1.0, max(float(existing.get("confidence", 0.0)), float(unit.get("confidence", 0.0))) + 0.08)
        existing["freshness_step"] = max(existing.get("freshness_step") or -1, unit.get("freshness_step") or -1)
        existing["supporting_outcome_ids"] = list(dict.fromkeys((existing.get("supporting_outcome_ids") or []) + (unit.get("supporting_outcome_ids") or [])))
        return
    self.experience_priority_units.append(unit)


def get_experience_priority_units(self, intent_family=None):
    units = list(getattr(self, "experience_priority_units", []) or [])
    if intent_family:
        units = [item for item in units if item.get("intent_family") == intent_family]
    return sorted(units, key=lambda item: (float(item.get("confidence", 0.0)), int(item.get("freshness_step", -1))), reverse=True)
```

- [ ] **Step 4: 让 `record_action_outcome(...)` 在现有 outcome 持久化之后自动更新经验单元**

```python
def record_action_outcome(self, outcome, recent_limit=8, failed_ttl=12, success_ttl=20):
    # existing outcome persistence...
    unit = self._normalize_experience_unit(outcome)
    if unit:
        self._merge_experience_unit(unit)
```

- [ ] **Step 5: 为旧存档加载补兼容**

```python
self.experience_priority_units = scratch_load.get("experience_priority_units", [])
scratch["experience_priority_units"] = self.experience_priority_units
```

- [ ] **Step 6: 运行测试，确认经验视图可构建且旧档兼容**

Run: `pytest test/test_action_outcomes.py test/test_scratch_legacy_load.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add reverie/backend_server/persona/memory_structures/scratch.py \
        reverie/backend_server/persona/cognitive_modules/action_outcomes.py \
        test/test_action_outcomes.py \
        test/test_scratch_legacy_load.py
git commit -m "feat: add prioritized runtime experience units"
```

### Task 2: 阶段1经验优先提示块

**Files:**
- Modify: `reverie/backend_server/persona/cognitive_modules/stage1_prompt_compiler.py`
- Modify: `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`
- Test: `test/test_demand_thinking_memory_context.py`
- Test: `test/test_decision_prompt_trace.py`

- [ ] **Step 1: 先写失败测试，固定阶段1要输出三段经验块**

```python
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from persona.cognitive_modules.stage1_prompt_compiler import build_experience_priority_texts


def test_build_experience_priority_texts_prefers_instance_failure_over_generic_success():
    scratch = SimpleNamespace(
        get_experience_priority_units=lambda intent_family=None: [
            {
                "experience_kind": "avoid",
                "intent_family": "restore_satiety",
                "resource_instance_key": "the ville:hobbs cafe:cafe:refrigerator",
                "resource_type": "refrigerator",
                "recommendation": "avoid_this_instance",
                "confidence": 0.88,
                "evidence_summary": "refrigerator at Hobbs Cafe was empty recently.",
            },
            {
                "experience_kind": "prefer",
                "intent_family": "restore_satiety",
                "resource_instance_key": "the ville:johnson park:park:apple tree",
                "resource_type": "apple tree",
                "recommendation": "prefer_this_instance",
                "confidence": 0.79,
                "evidence_summary": "apple tree worked well recently.",
            },
        ]
    )
    persona = SimpleNamespace(name="Isabella Rodriguez", scratch=scratch)

    blocks = build_experience_priority_texts(persona, intent_family="restore_satiety")

    assert "StrongAvoidExperience" in blocks
    assert "Hobbs Cafe" in blocks["StrongAvoidExperience"]
    assert "StrongPreferExperience" in blocks
    assert "apple tree" in blocks["StrongPreferExperience"]
    assert "instance-level experience over older generic memories" in blocks["ExperienceGuidance"]
```

- [ ] **Step 2: 运行测试，确认当前阶段1没有结构化经验块**

Run: `pytest test/test_demand_thinking_memory_context.py test/test_decision_prompt_trace.py -q`
Expected: FAIL，提示 `build_experience_priority_texts` 不存在或 prompt 中缺少经验块

- [ ] **Step 3: 在阶段1编译器中新增结构化经验块构造**

```python
def build_experience_priority_texts(persona, intent_family=None):
  scratch = getattr(persona, "scratch", None)
  if scratch is None:
    return {
      "StrongAvoidExperience": "None.",
      "StrongPreferExperience": "None.",
      "ExperienceGuidance": "No strong recent experience is available.",
    }

  units = []
  getter = getattr(scratch, "get_experience_priority_units", None)
  if callable(getter):
    units = getter(intent_family=intent_family)

  avoid_units = [item for item in units if item.get("experience_kind") == "avoid"][:2]
  prefer_units = [item for item in units if item.get("experience_kind") == "prefer"][:2]

  avoid_text = "None."
  if avoid_units:
    avoid_text = "\n".join(f"- {item.get('evidence_summary')}" for item in avoid_units)

  prefer_text = "None."
  if prefer_units:
    prefer_text = "\n".join(f"- {item.get('evidence_summary')}" for item in prefer_units)

  guidance = (
    "Prioritize strong recent instance-level experience over older generic memories. "
    "If a specific instance recently failed, prefer another feasible instance or another feasible source."
  )
  return {
    "StrongAvoidExperience": avoid_text,
    "StrongPreferExperience": prefer_text,
    "ExperienceGuidance": guidance,
  }
```

- [ ] **Step 4: 把阶段1 prompt 顺序改成“动机 > 强经验 > 可行性 > 泛背景”**

```python
experience_blocks = build_experience_priority_texts(persona, intent_family=intent_family)

final_prompt = final_prompt.replace(
    "Cooperative:",
    "StrongAvoidExperience:\n"
    f"{experience_blocks['StrongAvoidExperience']}\n"
    "StrongPreferExperience:\n"
    f"{experience_blocks['StrongPreferExperience']}\n"
    "ExperienceGuidance:\n"
    f"{experience_blocks['ExperienceGuidance']}\n"
    "Cooperative:"
)
```

- [ ] **Step 5: 在决策日志里把经验块写入 `stage1_dynamic_fields`，方便核查**

```python
"stage1_dynamic_fields": {
    ...
    "strong_avoid_experience_text": experience_blocks["StrongAvoidExperience"],
    "strong_prefer_experience_text": experience_blocks["StrongPreferExperience"],
    "experience_guidance_text": experience_blocks["ExperienceGuidance"],
}
```

- [ ] **Step 6: 运行测试，确认阶段1优先展示强经验**

Run: `pytest test/test_demand_thinking_memory_context.py test/test_decision_prompt_trace.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add reverie/backend_server/persona/cognitive_modules/stage1_prompt_compiler.py \
        reverie/backend_server/persona/prompt_template/run_gpt_prompt.py \
        test/test_demand_thinking_memory_context.py \
        test/test_decision_prompt_trace.py
git commit -m "feat: prioritize strong experience in stage1 prompts"
```

### Task 3: 阶段2经验护栏

**Files:**
- Modify: `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`
- Modify: `reverie/backend_server/persona/cognitive_modules/plan.py`
- Test: `test/test_action_mapping.py`
- Test: `test/test_gather_empty_source_replan.py`

- [ ] **Step 1: 先写失败测试，固定阶段2会收到 `ExperienceGuard`**

```python
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from persona.prompt_template.run_gpt_prompt import build_action_translation_experience_guard


def test_build_action_translation_experience_guard_exposes_avoid_and_prefer_units():
    scratch = SimpleNamespace(
        get_experience_priority_units=lambda intent_family=None: [
            {
                "experience_kind": "avoid",
                "intent_family": "restore_satiety",
                "resource_instance_key": "the ville:hobbs cafe:cafe:refrigerator",
                "resource_type": "refrigerator",
                "recommendation": "avoid_this_instance",
                "confidence": 0.88,
                "evidence_summary": "refrigerator at Hobbs Cafe was empty recently.",
            },
            {
                "experience_kind": "prefer",
                "intent_family": "restore_satiety",
                "resource_instance_key": "the ville:johnson park:park:apple tree",
                "resource_type": "apple tree",
                "recommendation": "prefer_this_instance",
                "confidence": 0.79,
                "evidence_summary": "apple tree worked well recently.",
            },
        ]
    )
    persona = SimpleNamespace(name="Isabella Rodriguez", scratch=scratch)

    guard = build_action_translation_experience_guard(persona, intent_family="restore_satiety")

    assert "Avoid exact instance" in guard
    assert "Hobbs Cafe" in guard
    assert "Preferred alternate sources" in guard
    assert "apple tree" in guard
```

- [ ] **Step 2: 运行测试，确认当前阶段2没有经验护栏文本**

Run: `pytest test/test_action_mapping.py test/test_gather_empty_source_replan.py -q`
Expected: FAIL，提示 `build_action_translation_experience_guard` 缺失或 action translation prompt 中无 `ExperienceGuard`

- [ ] **Step 3: 在阶段2 prompt 中增加 `ExperienceGuard`**

```python
def build_action_translation_experience_guard(persona, intent_family=None):
  getter = getattr(getattr(persona, "scratch", None), "get_experience_priority_units", None)
  units = getter(intent_family=intent_family) if callable(getter) else []
  avoid_units = [item for item in units if item.get("experience_kind") == "avoid"][:2]
  prefer_units = [item for item in units if item.get("experience_kind") == "prefer"][:2]
  lines = []
  for item in avoid_units:
    lines.append(f"- Avoid exact instance: {item.get('resource_instance_key')}")
  if prefer_units:
    preferred = ", ".join(item.get("resource_type") for item in prefer_units if item.get("resource_type"))
    lines.append(f"- Preferred alternate sources: {preferred}")
  if not lines:
    return "No strong recent experience guard."
  lines.append("- Strong recent instance-level evidence outweighs older generic success memories.")
  return "ExperienceGuard:\n" + "\n".join(lines)
```

- [ ] **Step 4: 把 `ExperienceGuard` 塞进 action translation prompt，并把日志里的 `decision_snapshot` 一并记录**

```python
experience_guard = build_action_translation_experience_guard(persona, intent_family=intent_family)

final_prompt = (
    final_prompt
    + "\n\n"
    + experience_guard
)

append_debug_log(
    "translation_verify.jsonl",
    merge_log_context(
        {
            "event": "experience_guard_snapshot",
            "persona": persona.name,
            "experience_guard": experience_guard,
        },
        persona=persona,
    )
)
```

- [ ] **Step 5: 在 `plan.py` 的食物源再解析路径里优先消费护栏，而不是只看泛化 `refrigerator`**

```python
if normalized_skill_id == "gather" and is_valid_gather_food_source(target):
    experience_preferred = _resolve_preferred_experience_food_source(persona, target)
    if experience_preferred:
        new_address = experience_preferred
    else:
        available_address = _resolve_food_source_address(persona, target)
        if available_address and available_address != new_address:
            new_address = available_address
```

- [ ] **Step 6: 运行测试，确认阶段2会把泛化食物意图收敛到经验更强的来源**

Run: `pytest test/test_action_mapping.py test/test_gather_empty_source_replan.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add reverie/backend_server/persona/prompt_template/run_gpt_prompt.py \
        reverie/backend_server/persona/cognitive_modules/plan.py \
        test/test_action_mapping.py \
        test/test_gather_empty_source_replan.py
git commit -m "feat: add experience guard to action translation"
```

### Task 4: 解析层经验排序与日志验证

**Files:**
- Modify: `reverie/backend_server/persona/cognitive_modules/action_target_resolver.py`
- Modify: `reverie/backend_server/persona/cognitive_modules/plan.py`
- Test: `test/test_gather_empty_source_replan.py`
- Test: `test/test_decision_constraints.py`

- [ ] **Step 1: 先写失败测试，固定解析层按经验分排序候选地址**

```python
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from persona.cognitive_modules.action_target_resolver import rank_candidate_addresses_by_experience


def test_rank_candidate_addresses_by_experience_demotes_recent_empty_instance():
    persona = SimpleNamespace(
        scratch=SimpleNamespace(
            get_experience_priority_units=lambda intent_family=None: [
                {
                    "experience_kind": "avoid",
                    "intent_family": "restore_satiety",
                    "resource_instance_key": "the ville:hobbs cafe:cafe:refrigerator",
                    "resource_type": "refrigerator",
                    "recommendation": "avoid_this_instance",
                    "confidence": 0.9,
                },
                {
                    "experience_kind": "prefer",
                    "intent_family": "restore_satiety",
                    "resource_instance_key": "the ville:johnson park:park:apple tree",
                    "resource_type": "apple tree",
                    "recommendation": "prefer_this_instance",
                    "confidence": 0.8,
                },
            ]
        )
    )

    ranked = rank_candidate_addresses_by_experience(
        persona,
        [
            "the Ville:Hobbs Cafe:cafe:refrigerator",
            "the Ville:Johnson Park:park:apple tree",
        ],
        intent_family="restore_satiety",
        target="refrigerator",
    )

    assert ranked[0] == "the Ville:Johnson Park:park:apple tree"
    assert ranked[-1] == "the Ville:Hobbs Cafe:cafe:refrigerator"
```

- [ ] **Step 2: 运行测试，确认当前 resolver 仍以旧的成功/失败地址列表为主**

Run: `pytest test/test_gather_empty_source_replan.py test/test_decision_constraints.py -q`
Expected: FAIL，提示 `rank_candidate_addresses_by_experience` 缺失或地址排序不符合预期

- [ ] **Step 3: 新增候选地址经验排序函数，优先看经验单元而不是简单黑名单**

```python
def rank_candidate_addresses_by_experience(persona, candidate_addresses, intent_family=None, target=None):
    getter = getattr(getattr(persona, "scratch", None), "get_experience_priority_units", None)
    units = getter(intent_family=intent_family) if callable(getter) else []
    score_map = {}
    for address in candidate_addresses or []:
        normalized = _normalize_text(address)
        score = 0.0
        for unit in units:
            if unit.get("resource_instance_key") != normalized:
                continue
            confidence = float(unit.get("confidence", 0.0) or 0.0)
            if unit.get("experience_kind") == "avoid":
                score -= 2.0 * confidence
            elif unit.get("experience_kind") == "prefer":
                score += 1.5 * confidence
        score_map[address] = score
    return sorted(candidate_addresses or [], key=lambda item: score_map.get(item, 0.0), reverse=True)
```

- [ ] **Step 4: 在 `resolve_known_object_address(...)` 和 `_resolve_food_source_address(...)` 中统一接入该排序**

```python
candidate_addresses = rank_candidate_addresses_by_experience(
    persona,
    candidate_addresses,
    intent_family="restore_satiety" if _normalize_text(target) in {"refrigerator", "apple tree", "cafe counter", "stove"} else None,
    target=target,
)
address = _pick_preferred_address(candidate_addresses, preferred_addresses, blocked_addresses)
```

- [ ] **Step 5: 把经验排序结果落日志，方便验证“不是没起作用，而是如何起作用”**

```python
append_debug_log(
    "translation_verify.jsonl",
    merge_log_context(
        {
            "event": "experience_ranked_candidates",
            "persona": persona.name,
            "target": target,
            "candidate_addresses": candidate_addresses,
            "ranked_addresses": ranked_addresses,
        },
        persona=persona,
    )
)
```

- [ ] **Step 6: 运行测试，确认解析层会自然回避空实例并偏向强正经验实例**

Run: `pytest test/test_gather_empty_source_replan.py test/test_decision_constraints.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add reverie/backend_server/persona/cognitive_modules/action_target_resolver.py \
        reverie/backend_server/persona/cognitive_modules/plan.py \
        test/test_gather_empty_source_replan.py \
        test/test_decision_constraints.py
git commit -m "feat: rank action targets by strong experience"
```
