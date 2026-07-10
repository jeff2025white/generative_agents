# Action Outcome Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为技能执行链路落地 `ActionOutcomeRecord` MVP，实现统一结果事实、`scratch` 运行时聚合、`action_outcome.jsonl` 落盘，并逐步接入记忆与决策消费。

**Architecture:** 先把“失败/成功执行结果”收口到一个统一 outcome builder，再通过 `scratch.record_action_outcome(...)` 同步更新短期运行时视图与 JSONL 日志。第一阶段优先打通失败约束与实例级 cooldown，第二阶段再补 effects、memory projection、Stage1/Stage2 提示块。

**Tech Stack:** Python, unittest/pytest, `Scratch` 持久化, `append_debug_log` JSONL 日志, `AssociativeMemory`

---

### Task 1: 定义 Outcome MVP Schema

**Files:**
- Create: `reverie/backend_server/persona/cognitive_modules/action_outcomes.py`
- Test: `test/test_action_outcomes.py`

- [ ] **Step 1: 写失败测试，固定 MVP 字段结构与原因分类**

```python
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from persona.cognitive_modules.action_outcomes import (
    classify_reason,
    build_action_outcome_record,
)


class ActionOutcomeRecordTests(unittest.TestCase):
    def _build_persona(self):
        scratch = SimpleNamespace(
            curr_step=161,
            curr_time=None,
            act_address="the Ville:Hobbs Cafe:cafe:refrigerator",
            act_description="opening the refrigerator to gather food items",
            act_command={
                "skill_id": "gather",
                "target": "refrigerator",
                "intent_family": "restore_satiety",
                "raw_action": "Gather",
            },
            inventory={},
            satiety=18.0,
            stamina=62.0,
            health=91.0,
            mood=55.0,
            current_action_record={
                "decision_id": "Isabella_Rodriguez-161-ab12cd34",
                "resolved_target": "refrigerator",
                "resolved_address": "the Ville:Hobbs Cafe:cafe:refrigerator",
                "resolution_kind": "known_object",
            },
        )
        return SimpleNamespace(name="Isabella Rodriguez", scratch=scratch)

    def test_classify_reason_maps_resource_empty(self):
        self.assertEqual(classify_reason("resource_empty"), "resource_state")

    def test_build_action_outcome_record_returns_mvp_fields(self):
        persona = self._build_persona()
        outcome = build_action_outcome_record(
            persona,
            result="failed",
            reason="resource_empty",
            payload={"effective_source": "refrigerator"},
        )

        self.assertEqual(outcome["schema_version"], 1)
        self.assertEqual(outcome["persona"], "Isabella Rodriguez")
        self.assertEqual(outcome["action"]["skill_id"], "gather")
        self.assertEqual(outcome["action"]["target"], "refrigerator")
        self.assertEqual(
            outcome["action"]["target_address"],
            "the Ville:Hobbs Cafe:cafe:refrigerator",
        )
        self.assertEqual(outcome["execution"]["result"], "failed")
        self.assertEqual(outcome["execution"]["reason"], "resource_empty")
        self.assertEqual(outcome["execution"]["reason_class"], "resource_state")
        self.assertEqual(
            outcome["resource_context"]["resource_instance_key"],
            "the ville:hobbs cafe:cafe:refrigerator",
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认当前缺少 outcome 模块**

Run: `pytest test/test_action_outcomes.py -q`
Expected: FAIL，提示 `ModuleNotFoundError` 或 `cannot import name 'build_action_outcome_record'`

- [ ] **Step 3: 实现最小 outcome builder**

```python
import hashlib
from datetime import datetime


def classify_reason(reason):
    normalized = str(reason or "").strip().lower()
    mapping = {
        "resource_empty": "resource_state",
        "consume_no_food_available": "precondition",
        "path_not_found": "navigation",
        "target_not_found": "resolution",
        "invalid_food_source": "resolution",
    }
    return mapping.get(normalized, "other")


def _lower_resource_instance_key(target_address):
    text = str(target_address or "").strip()
    return text.lower() if text else None


def _build_outcome_id(persona_name, curr_step, skill_id, target_address, result, reason):
    base = "|".join(
        [
            str(persona_name or ""),
            str(curr_step or ""),
            str(skill_id or ""),
            str(target_address or ""),
            str(result or ""),
            str(reason or ""),
        ]
    )
    digest = hashlib.md5(base.encode("utf-8")).hexdigest()[:10]
    return f"{persona_name}-{curr_step}-{digest}"


def build_action_outcome_record(persona, result, reason=None, payload=None, effects=None):
    scratch = getattr(persona, "scratch", None)
    action_command = getattr(scratch, "act_command", None) or {}
    current_record = getattr(scratch, "current_action_record", None) or {}
    target_address = current_record.get("resolved_address") or getattr(scratch, "act_address", None)
    skill_id = action_command.get("skill_id")
    target = action_command.get("target")
    curr_step = getattr(scratch, "curr_step", None)

    return {
        "schema_version": 1,
        "outcome_id": _build_outcome_id(persona.name, curr_step, skill_id, target_address, result, reason),
        "sim_code": getattr(persona, "sim_code", None),
        "persona": persona.name,
        "curr_step": curr_step,
        "sim_time": getattr(scratch, "curr_time", None).strftime("%Y-%m-%d %H:%M:%S") if getattr(scratch, "curr_time", None) else None,
        "wall_ts": datetime.now().astimezone().isoformat(),
        "decision_context": {
            "decision_id": current_record.get("decision_id"),
            "dominant_motive": current_record.get("dominant_motive"),
        },
        "action": {
            "skill_id": skill_id,
            "raw_action": action_command.get("raw_action"),
            "intent_family": action_command.get("intent_family"),
            "target": target,
            "target_type": current_record.get("target_type"),
            "target_address": target_address,
            "resolved_target": current_record.get("resolved_target") or target,
            "resolution_kind": current_record.get("resolution_kind"),
            "detail": getattr(scratch, "act_description", None),
        },
        "execution": {
            "result": result,
            "reason": reason,
            "reason_class": classify_reason(reason),
        },
        "effects": effects or {
            "self_attribute_effects": {"satiety": 0.0, "stamina": 0.0, "health": 0.0, "mood": 0.0},
            "inventory_delta": {},
            "progress_score": 0.0,
        },
        "resource_context": {
            "resource_type": target,
            "resource_instance_key": _lower_resource_instance_key(target_address),
        },
        "experience_scoring": {
            "effective_score": 0.0,
            "should_promote_to_experience": False,
        },
        "memory_projection": {},
    }
```

- [ ] **Step 4: 运行测试，确认 schema 稳定**

Run: `pytest test/test_action_outcomes.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add test/test_action_outcomes.py reverie/backend_server/persona/cognitive_modules/action_outcomes.py
git commit -m "feat: add action outcome mvp builder"
```

### Task 2: 为 Scratch 增加 Outcome 聚合视图与持久化

**Files:**
- Modify: `reverie/backend_server/persona/memory_structures/scratch.py`
- Test: `test/test_scratch_legacy_load.py`

- [ ] **Step 1: 写失败测试，固定 `scratch` 新字段和保留策略**

```python
def test_action_outcome_runtime_views_persist_across_save_and_load(self):
    scratch = Scratch(str(ROOT / "test" / "__missing_scratch__.json"))
    scratch.curr_time = datetime(2026, 7, 10, 12, 0, 0)
    scratch.act_start_time = datetime(2026, 7, 10, 12, 0, 0)
    scratch.curr_step = 161

    outcome = {
        "schema_version": 1,
        "outcome_id": "Isabella-161-abc",
        "persona": "Isabella Rodriguez",
        "curr_step": 161,
        "action": {
            "skill_id": "gather",
            "target": "refrigerator",
            "target_address": "the Ville:Hobbs Cafe:cafe:refrigerator",
        },
        "execution": {
            "result": "failed",
            "reason": "resource_empty",
            "reason_class": "resource_state",
        },
        "effects": {
            "self_attribute_effects": {"satiety": 0.0, "stamina": 0.0, "health": 0.0, "mood": 0.0},
            "inventory_delta": {},
            "progress_score": 0.0,
        },
        "resource_context": {
            "resource_instance_key": "the ville:hobbs cafe:cafe:refrigerator",
        },
    }

    scratch.record_action_outcome(outcome)

    self.assertEqual(scratch.last_action_outcome["outcome_id"], "Isabella-161-abc")
    self.assertEqual(len(scratch.recent_action_outcomes), 1)
    self.assertEqual(scratch.failed_resource_instances[0]["reason"], "resource_empty")
```

- [ ] **Step 2: 运行测试，确认 `Scratch` 还没有新字段**

Run: `pytest test/test_scratch_legacy_load.py -q`
Expected: FAIL，提示 `record_action_outcome` 缺失或 `last_action_outcome` 不存在

- [ ] **Step 3: 在 `Scratch` 中实现运行时 outcome 视图**

```python
self.last_action_outcome = scratch_load.get("last_action_outcome")
self.recent_action_outcomes = scratch_load.get("recent_action_outcomes", [])
self.failed_resource_instances = scratch_load.get("failed_resource_instances", [])
self.successful_resource_instances = scratch_load.get("successful_resource_instances", [])
```

```python
scratch["last_action_outcome"] = self.last_action_outcome
scratch["recent_action_outcomes"] = self.recent_action_outcomes
scratch["failed_resource_instances"] = self.failed_resource_instances
scratch["successful_resource_instances"] = self.successful_resource_instances
```

```python
def record_action_outcome(self, outcome, recent_limit=8, failed_ttl=12, success_ttl=20):
    if not isinstance(outcome, dict) or not outcome:
        return None
    self.last_action_outcome = outcome
    self.recent_action_outcomes = (self.recent_action_outcomes or []) + [outcome]
    self.recent_action_outcomes = self.recent_action_outcomes[-recent_limit:]

    action = outcome.get("action") or {}
    execution = outcome.get("execution") or {}
    curr_step = outcome.get("curr_step", self.curr_step)
    target = action.get("target")
    target_address = action.get("target_address")

    if execution.get("reason_class") == "resource_state" and target_address:
        self.failed_resource_instances = [
            item for item in (self.failed_resource_instances or [])
            if (item.get("expires_after_step") or curr_step) >= (self.curr_step or curr_step)
        ]
        self.failed_resource_instances.append(
            {
                "target": target,
                "target_address": target_address,
                "reason": execution.get("reason"),
                "curr_step": curr_step,
                "expires_after_step": (curr_step or 0) + failed_ttl,
            }
        )

    if execution.get("result") == "success" and target_address:
        self.successful_resource_instances = [
            item for item in (self.successful_resource_instances or [])
            if (item.get("expires_after_step") or curr_step) >= (self.curr_step or curr_step)
        ]
        self.successful_resource_instances.append(
            {
                "target": target,
                "target_address": target_address,
                "progress_score": ((outcome.get("effects") or {}).get("progress_score") or 0.0),
                "curr_step": curr_step,
                "expires_after_step": (curr_step or 0) + success_ttl,
            }
        )
    return outcome
```

- [ ] **Step 4: 运行测试，确认持久化往返通过**

Run: `pytest test/test_scratch_legacy_load.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add test/test_scratch_legacy_load.py reverie/backend_server/persona/memory_structures/scratch.py
git commit -m "feat: persist action outcome runtime views"
```

### Task 3: 打通失败路径的 Outcome 写入与 JSONL 落盘

**Files:**
- Modify: `reverie/backend_server/persona/memory_structures/scratch.py:1690-1895`
- Modify: `reverie/backend_server/persona/cognitive_modules/execute.py:337-380`
- Modify: `reverie/backend_server/persona/cognitive_modules/skill_packs/base.py:50-91`
- Modify: `reverie/backend_server/persona/cognitive_modules/debug_log.py`
- Test: `test/test_decision_constraints.py`
- Test: `test/test_action_outcomes.py`

- [ ] **Step 1: 写失败测试，确认 `resource_empty` 不再只靠 `navigation_failure` 单点传递**

```python
def test_build_invalid_targets_uses_failed_instances_for_non_empty_failures(self):
    scratch = type(
        "Scratch",
        (),
        {
            "failed_resource_instances": [
                {
                    "target": "apple tree",
                    "target_address": "the Ville:Johnson Park:park:apple tree",
                    "reason": "path_not_found",
                    "curr_step": 10,
                    "expires_after_step": 16,
                }
            ],
            "curr_step": 12,
            "get_recent_navigation_failure": lambda self, max_age_steps=6: None,
        },
    )()

    invalid_targets = build_invalid_targets(scratch)

    self.assertEqual(invalid_targets, ["apple tree"])
```

```python
def test_record_action_outcome_writes_jsonl(self):
    from unittest.mock import patch

    persona = self._build_persona()
    outcome = build_action_outcome_record(persona, result="failed", reason="resource_empty")

    with patch("persona.memory_structures.scratch.append_debug_log") as mock_log:
        persona.scratch.record_action_outcome(outcome)

    mock_log.assert_called()
    self.assertEqual(mock_log.call_args.args[0], "action_outcome")
```

- [ ] **Step 2: 运行测试，确认当前消费逻辑仍未识别新视图**

Run: `pytest test/test_decision_constraints.py test/test_action_outcomes.py -q`
Expected: FAIL，提示 `failed_resource_instances` 未被消费，或 `action_outcome` 日志尚未写入

- [ ] **Step 3: 在 `record_action_outcome()` 内落盘，并让失败路径统一调用**

```python
append_debug_log(
    "action_outcome",
    {
        "persona": outcome.get("persona"),
        "curr_step": outcome.get("curr_step"),
        "sim_time": outcome.get("sim_time"),
        "outcome": outcome,
    },
)
```

```python
def fail_execution(self, reason, payload=None):
    payload = payload or {}
    outcome = build_action_outcome_record(
        self._persona_ref,
        result="failed",
        reason=reason,
        payload=payload,
    ) if getattr(self, "_persona_ref", None) else None
    if outcome:
        self.record_action_outcome(outcome)
    ...
```

```python
def finish_failure(self, persona, reason, payload=None):
    if hasattr(persona.scratch, "attach_persona_ref"):
        persona.scratch.attach_persona_ref(persona)
    if hasattr(persona.scratch, "fail_execution"):
        persona.scratch.fail_execution(reason, payload=payload)
```

- [ ] **Step 4: 让约束层优先读取 failed instances，而不是只看 `navigation_failure`**

```python
def build_invalid_targets(scratch, max_age_steps=6):
    failed_instances = getattr(scratch, "failed_resource_instances", None) or []
    curr_step = getattr(scratch, "curr_step", None)
    collected = []
    for item in failed_instances:
        expires_after = item.get("expires_after_step")
        if curr_step is not None and expires_after is not None and expires_after < curr_step:
            continue
        reason = str(item.get("reason") or "").strip().lower()
        if reason == "resource_empty":
            continue
        collected.append(item.get("target"))
    if collected:
        return _normalize_invalid_targets(collected)
    ...
```

- [ ] **Step 5: 运行测试，确认失败路径已打通**

Run: `pytest test/test_decision_constraints.py test/test_action_outcomes.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add test/test_decision_constraints.py test/test_action_outcomes.py reverie/backend_server/persona/memory_structures/scratch.py reverie/backend_server/persona/cognitive_modules/execute.py reverie/backend_server/persona/cognitive_modules/skill_packs/base.py reverie/backend_server/persona/cognitive_modules/debug_log.py
git commit -m "feat: emit failed action outcomes"
```

### Task 4: 补成功结果、Effects 与 Experience Projection

**Files:**
- Modify: `reverie/backend_server/persona/cognitive_modules/action_outcomes.py`
- Modify: `reverie/backend_server/persona/cognitive_modules/memory_effects.py`
- Modify: `reverie/backend_server/persona/cognitive_modules/skill_packs/gather_skill.py`
- Modify: `reverie/backend_server/persona/cognitive_modules/skill_packs/consume_skill.py`
- Modify: `reverie/backend_server/persona/cognitive_modules/skill_packs/base.py`
- Test: `test/test_action_outcomes.py`
- Test: `test/test_gather_empty_source_replan.py`
- Test: `test/test_klaus_isabella_eating_fix.py`

- [ ] **Step 1: 写失败测试，固定 `effects` 与 `memory_projection` 的最小契约**

```python
def test_build_action_outcome_record_includes_memory_projection_for_promoted_experience(self):
    persona = self._build_persona()
    outcome = build_action_outcome_record(
        persona,
        result="success",
        reason=None,
        effects={
            "self_attribute_effects": {"satiety": 12.0, "stamina": 0.0, "health": 0.0, "mood": 0.0},
            "inventory_delta": {"apple": -1},
            "progress_score": 1.0,
        },
    )

    self.assertEqual(outcome["execution"]["result"], "success")
    self.assertGreaterEqual(outcome["experience_scoring"]["effective_score"], 0.55)
    self.assertTrue(outcome["experience_scoring"]["should_promote_to_experience"])
    self.assertIn("description", outcome["memory_projection"])
    self.assertIn("keywords", outcome["memory_projection"])
```

- [ ] **Step 2: 运行测试，确认 success path 还没有 effects scoring**

Run: `pytest test/test_action_outcomes.py -q`
Expected: FAIL，提示 `memory_projection` 缺字段或 `should_promote_to_experience` 为 `False`

- [ ] **Step 3: 在 outcome builder 中实现最小 scoring 与 projection**

```python
def score_action_outcome(effects, reason, dominant_motive=None):
    effects = effects or {}
    self_effects = (effects.get("self_attribute_effects") or {})
    self_effect_magnitude = min(
        1.0,
        sum(abs(float(v or 0.0)) for v in self_effects.values()) / 20.0,
    )
    failure_learning_value = 0.72 if str(reason or "").strip().lower() in {
        "resource_empty",
        "consume_no_food_available",
        "path_not_found",
    } else 0.0
    alignment = 0.95 if dominant_motive in {"satiety", "stamina", "health", "mood"} else 0.3
    base_significance = min(1.0, self_effect_magnitude + failure_learning_value + alignment * 0.2)
    effective_score = round(base_significance, 3)
    return {
        "self_effect_magnitude": round(self_effect_magnitude, 3),
        "other_effect_magnitude": 0.0,
        "failure_learning_value": round(failure_learning_value, 3),
        "novelty_value": 0.0,
        "dominant_motive_alignment": round(alignment, 3),
        "base_significance": effective_score,
        "recency_weight": 1.0,
        "effective_score": effective_score,
        "should_promote_to_experience": effective_score >= 0.55,
    }
```

```python
def build_memory_projection(persona, outcome):
    action = outcome.get("action") or {}
    execution = outcome.get("execution") or {}
    description = (
        f"{persona.name} experienced {execution.get('result')} while using "
        f"{action.get('skill_id')} on {action.get('target')} at {action.get('target_address')}."
    )
    return {
        "source_outcome_id": outcome.get("outcome_id"),
        "memory_type": "event",
        "subject": persona.name,
        "predicate": "experienced",
        "object": "execution_result",
        "description": description,
        "embedding_text": description,
        "keywords": [
            str(action.get("skill_id") or "").lower(),
            str(action.get("target") or "").lower(),
            str(execution.get("result") or "").lower(),
            str(execution.get("reason") or "").lower(),
        ],
        "poignancy": round(4.0 + outcome["experience_scoring"]["effective_score"] * 4.0, 2),
        "attribute_effects": (outcome.get("effects") or {}).get("self_attribute_effects") or {},
        "memory_tags": {
            "skill_id": action.get("skill_id"),
            "target": action.get("target"),
            "target_address": action.get("target_address"),
            "reason": execution.get("reason"),
        },
    }
```

- [ ] **Step 4: 在技能成功路径把 `effects` 传给 `finish_success()`，并按阈值写入 AssociativeMemory**

```python
def finish_success(self, persona, *, action_command=None, action_event=None, action_description=None, action_address=None, outcome_effects=None):
    if hasattr(persona.scratch, "attach_persona_ref"):
        persona.scratch.attach_persona_ref(persona)
    persona.scratch.mark_action_completed(
        action_command=action_command or persona.scratch.act_command,
        action_event=action_event or persona.scratch.act_event,
        action_description=action_description or persona.scratch.act_description,
        action_address=action_address or persona.scratch.act_address,
        outcome_effects=outcome_effects,
    )
```

```python
self.finish_success(
    persona,
    outcome_effects={
        "self_attribute_effects": attribute_effects,
        "inventory_delta": {"apple": 2},
        "progress_score": 0.6,
    },
)
```

```python
def record_projected_action_experience(persona, outcome):
    projection = (outcome or {}).get("memory_projection") or {}
    if not projection or not (outcome.get("experience_scoring") or {}).get("should_promote_to_experience"):
        return None
    return persona.a_mem.add_event(
        persona.scratch.curr_time,
        None,
        projection["subject"],
        projection["predicate"],
        projection["object"],
        projection["description"],
        set(projection["keywords"]),
        float(projection["poignancy"]),
        (projection["embedding_text"], get_embedding(projection["embedding_text"])),
        None,
        attribute_effects=projection.get("attribute_effects"),
    )
```

- [ ] **Step 5: 运行测试，确认 success path 与经验投影通过**

Run: `pytest test/test_action_outcomes.py test/test_gather_empty_source_replan.py test/test_klaus_isabella_eating_fix.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add test/test_action_outcomes.py test/test_gather_empty_source_replan.py test/test_klaus_isabella_eating_fix.py reverie/backend_server/persona/cognitive_modules/action_outcomes.py reverie/backend_server/persona/cognitive_modules/memory_effects.py reverie/backend_server/persona/cognitive_modules/skill_packs/gather_skill.py reverie/backend_server/persona/cognitive_modules/skill_packs/consume_skill.py reverie/backend_server/persona/cognitive_modules/skill_packs/base.py
git commit -m "feat: project action outcomes into experience memory"
```

### Task 5: 接入 Stage1/Stage2 与 Resolver 消费块

**Files:**
- Modify: `reverie/backend_server/persona/cognitive_modules/decision_constraints.py`
- Modify: `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`
- Modify: `reverie/backend_server/persona/cognitive_modules/intent_memory.py`
- Test: `test/test_demand_thinking_memory_context.py`
- Test: `test/test_decision_constraints.py`

- [ ] **Step 1: 写失败测试，固定 Recent Action Outcomes 和 Translation Constraints 的提示块**

```python
def test_decision_capsule_prefers_recent_action_outcomes_block(self):
    persona = SimpleNamespace(
        scratch=SimpleNamespace(
            inventory={},
            curr_time=datetime.datetime(2026, 7, 2, 9, 35, 0),
            satiety=18.0,
            stamina=62.0,
            health=91.0,
            mood=55.0,
            get_recent_navigation_failure=lambda max_age_steps=6: None,
            get_recent_action_observation=lambda max_age_steps=6: None,
            recent_action_outcomes=[
                {
                    "action": {
                        "skill_id": "gather",
                        "target": "refrigerator",
                        "target_address": "the Ville:Hobbs Cafe:cafe:refrigerator",
                    },
                    "execution": {
                        "result": "failed",
                        "reason": "resource_empty",
                    },
                }
            ],
        )
    )

    capsule = prompt_module.build_decision_capsule(
        persona,
        temporal_context="- Current Time: Wednesday July 02, 2026, 09:35 AM",
        status_summary="Satiety is low and food should become the top priority.",
        rules="Use recent execution outcomes.",
        cooperative_context="No special cooperative tasks are active nearby.",
        nearby_resources=["refrigerator (idle/normal)", "apple tree (idle/normal)"],
        last_action_desc="opening the refrigerator to gather food items",
        intent_memory_summary="Food-related experience is available.",
        decision_convergence_hint="Choose the immediate next action only.",
    )

    self.assertIn("Recent Action Outcomes:", capsule)
    self.assertIn("resource_empty", capsule)
```

- [ ] **Step 2: 运行测试，确认 prompt 仍只消费 `last_action_observation`**

Run: `pytest test/test_demand_thinking_memory_context.py test/test_decision_constraints.py -q`
Expected: FAIL，提示缺少 `Recent Action Outcomes:` 块或 resolver 仍未优先按实例级 cooldown 过滤

- [ ] **Step 3: 在 prompt helper 中压缩 recent outcomes**

```python
def _build_recent_action_outcomes_block(scratch, max_items=3):
    outcomes = list(getattr(scratch, "recent_action_outcomes", []) or [])[-max_items:]
    if not outcomes:
        return None
    lines = ["Recent Action Outcomes:"]
    for item in outcomes:
        action = item.get("action") or {}
        execution = item.get("execution") or {}
        lines.append(
            "- "
            + f"{execution.get('result')} | {action.get('skill_id')} | {action.get('target')} | "
            + f"{action.get('target_address')} | reason={execution.get('reason') or 'none'}"
        )
    return "\n".join(lines)
```

```python
recent_outcomes_block = _build_recent_action_outcomes_block(getattr(persona, "scratch", None))
if recent_outcomes_block:
    special_instruction += "\n" + recent_outcomes_block
```

- [ ] **Step 4: 在约束层实现实例级过滤与成功偏好入口**

```python
def filter_failed_resource_instances(scratch, target, candidates):
    failed = {
        str(item.get("target_address") or "").strip().lower()
        for item in (getattr(scratch, "failed_resource_instances", None) or [])
        if str(item.get("target") or "").strip().lower() == str(target or "").strip().lower()
    }
    return [item for item in candidates if str(item.get("address") or "").strip().lower() not in failed]
```

- [ ] **Step 5: 运行测试，确认 Stage1/Stage2/Resolver 可读 outcome 聚合**

Run: `pytest test/test_demand_thinking_memory_context.py test/test_decision_constraints.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add test/test_demand_thinking_memory_context.py test/test_decision_constraints.py reverie/backend_server/persona/cognitive_modules/decision_constraints.py reverie/backend_server/persona/prompt_template/run_gpt_prompt.py reverie/backend_server/persona/cognitive_modules/intent_memory.py
git commit -m "feat: consume action outcomes in prompts and constraints"
```

### Task 6: 全链路回归与清理

**Files:**
- Test: `test/test_action_outcomes.py`
- Test: `test/test_scratch_legacy_load.py`
- Test: `test/test_decision_constraints.py`
- Test: `test/test_demand_thinking_memory_context.py`
- Test: `test/test_gather_empty_source_replan.py`
- Test: `test/test_klaus_isabella_eating_fix.py`

- [ ] **Step 1: 运行聚焦回归集**

Run: `pytest test/test_action_outcomes.py test/test_scratch_legacy_load.py test/test_decision_constraints.py test/test_demand_thinking_memory_context.py test/test_gather_empty_source_replan.py test/test_klaus_isabella_eating_fix.py -q`
Expected: PASS

- [ ] **Step 2: 运行 linter/诊断，确认新增字段和导入无错误**

Run: `python -m pytest test/test_action_outcomes.py -q`
Expected: PASS，且本次改动文件无新增诊断错误

- [ ] **Step 3: 手工验证日志形态**

Run: `tail -n 5 logs/action_outcome.jsonl`
Expected: 每行包含 `persona`、`curr_step`、`sim_time`、`outcome.schema_version`、`outcome.action.target_address`

- [ ] **Step 4: 提交**

```bash
git add test/test_action_outcomes.py test/test_scratch_legacy_load.py test/test_decision_constraints.py test/test_demand_thinking_memory_context.py test/test_gather_empty_source_replan.py test/test_klaus_isabella_eating_fix.py
git commit -m "test: cover action outcome rollout"
```
