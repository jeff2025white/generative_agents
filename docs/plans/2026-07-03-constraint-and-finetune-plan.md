# Constraint And Training-Prep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 先用“最小输出约束”打断 `navigation_failure` 后重复输出失败目标的回环，并同步完成日志字段、存储与格式化改造，为后续高质量训练样本沉淀做好准备；模型微调在样本数量与质量达标后再单独启动。

**Architecture:** 本计划分三个阶段。第一阶段在现有 `decision capsule -> LLM -> action translation -> execute` 链路中插入“无效目标声明、候选过滤、单次重试校验”三层最小约束，只排除当前已知错误项，不替 LLM 决定正解。第二阶段改造日志契约，为每次决策补齐 `decision_id`、最终 prompt、约束命中、执行结果、样本标签等字段，并沉淀成统一 JSONL 存储格式。第三阶段只做训练准备与 readiness gate：从日志抽取候选样本、统计样本质量与覆盖度，只有当样本量与标签完整性达标后，才另开一份模型微调实施计划。

**Tech Stack:** Python, Ollama, JSONL logs, existing persona planning pipeline, `python -m unittest`, markdown docs

---

## File Map

### Existing files to modify

- `g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py`
  - 扩展 `Decision Capsule`，注入 `InvalidTargets`、最终 prompt 落盘入口与训练准备字段；过滤失败候选资源。
- `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py`
  - 在联合决策/双阶段决策后增加最小输出校验与单次重试入口；生成 `decision_id`，记录约束命中、执行结果与训练准备日志。
- `g:\generative_agents\reverie\backend_server\persona\memory_structures\scratch.py`
  - 为“最近失败目标黑名单”提供读取接口，保证短期 step 内可用。
- `g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\demand_decision_thinking_v1.txt`
  - 补充 `InvalidTargets` 语义说明，要求本步禁选。
- `g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\joint_decision_v1.txt`
  - 补充结构化返回前的无效目标约束。
- `g:\generative_agents\reverie\backend_server\persona\prompt_template\gpt_structure.py`
  - 统一 LLM 请求日志，补齐 `prompt_kind`、`prompt_hash`、`decision_id`、重试信息与训练准备所需字段。
- `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\debug_log.py`
  - 复用现有 JSONL 落盘工具，确保新增日志遵循统一字段结构。
- `g:\generative_agents\test\test_demand_thinking_memory_context.py`
  - 扩展到 `InvalidTargets`、最终 prompt 落盘与资源过滤断言。
- `g:\generative_agents\test\test_joint_decision_pipeline.py`
  - 扩展到输出后校验与单次重试逻辑。

### New files to create

- `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\decision_constraints.py`
  - 封装“最近失败目标收集、资源过滤、输出合法性检查、重试反馈构造”。
- `g:\generative_agents\test\test_decision_constraints.py`
  - 覆盖最近失败目标黑名单、资源过滤、非法目标重试、一次性重试上限。
- `g:\generative_agents\test\test_decision_training_logs.py`
  - 覆盖 `decision_id`、最终 prompt、约束命中与执行结果日志结构。
- `g:\generative_agents\test\check_invalid_target_behavior.py`
  - 离线检查脚本，统计日志中“重复失败 target”的比例、约束触发次数与 `decision_id` 聚合结果。
- `g:\generative_agents\reverie\backend_server\persona\training\training_candidate_builder.py`
  - 把日志转成训练候选样本池，不直接生成最终微调数据。
- `g:\generative_agents\test\test_training_candidate_builder.py`
  - 覆盖训练候选样本格式与过滤规则。
- `g:\generative_agents\test\check_extract_training_candidates.py`
  - 从现有日志提取训练候选样本并输出统计摘要。
- `g:\generative_agents\docs\llm_constraint_and_finetune_workflow.md`
  - 记录约束层语义、日志字段契约、样本沉淀流程、readiness gate 与后续微调前置条件。

---

### Task 1: 建立最近失败目标黑名单与 Prompt 注入

**Files:**
- Create: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\decision_constraints.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\memory_structures\scratch.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\demand_decision_thinking_v1.txt`
- Modify: `g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\joint_decision_v1.txt`
- Test: `g:\generative_agents\test\test_decision_constraints.py`
- Test: `g:\generative_agents\test\test_demand_thinking_memory_context.py`

- [ ] **Step 1: 写失败测试，固定最近失败目标黑名单格式**

```python
# g:\generative_agents\test\test_decision_constraints.py
import unittest

from persona.cognitive_modules.decision_constraints import build_invalid_targets


class InvalidTargetTests(unittest.TestCase):
    def test_build_invalid_targets_from_recent_navigation_failure(self):
        scratch = type("Scratch", (), {
            "get_recent_navigation_failure": lambda self, max_age_steps=6: {
                "target": "apple tree",
                "target_address": "the Ville:Johnson Park:park:apple tree",
                "reason": "path_not_found",
            }
        })()

        invalid_targets = build_invalid_targets(scratch)

        self.assertEqual(invalid_targets, ["apple tree"])
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```bash
python -m unittest test.test_decision_constraints
```

Expected:

```text
ERROR: No module named 'persona.cognitive_modules.decision_constraints'
```

- [ ] **Step 3: 实现最小黑名单收集器**

```python
# g:\generative_agents\reverie\backend_server\persona\cognitive_modules\decision_constraints.py
def build_invalid_targets(scratch, max_age_steps=6):
    failure = scratch.get_recent_navigation_failure(max_age_steps=max_age_steps)
    if not failure:
        return []

    target = (failure.get("target") or "").strip()
    if not target:
        return []
    return [target]
```

- [ ] **Step 4: 把 `InvalidTargets` 注入 `Decision Capsule`，并在模板中声明“本步禁选”**

```python
# g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py
from persona.cognitive_modules.decision_constraints import build_invalid_targets

invalid_targets = build_invalid_targets(persona.scratch)
if invalid_targets:
    capsule_lines.append(
      "InvalidTargets: "
      + ", ".join(invalid_targets)
      + ". These targets are invalid for the next immediate step and must not be selected."
    )
```

```text
# g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\demand_decision_thinking_v1.txt
Priority Rules:
...
5. If a target appears in InvalidTargets, it is forbidden for this immediate step.
```

- [ ] **Step 5: 扩展测试，验证 `InvalidTargets` 已进入 Prompt**

```python
# g:\generative_agents\test\test_demand_thinking_memory_context.py
self.assertIn("InvalidTargets:", capsule)
self.assertIn("apple tree", capsule)
self.assertIn("must not be selected", capsule)
```

- [ ] **Step 6: 运行测试，确认通过**

Run:

```bash
python -m unittest test.test_decision_constraints test.test_demand_thinking_memory_context
```

Expected:

```text
OK
```

- [ ] **Step 7: 提交**

```bash
git add g:\generative_agents\reverie\backend_server\persona\cognitive_modules\decision_constraints.py g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\demand_decision_thinking_v1.txt g:\generative_agents\reverie\backend_server\persona\prompt_template\v2\joint_decision_v1.txt g:\generative_agents\test\test_decision_constraints.py g:\generative_agents\test\test_demand_thinking_memory_context.py
git commit -m "feat(prompt): add invalid target constraint injection"
```

---

### Task 2: 对候选资源做过滤，减少失败目标再次进入候选空间

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\decision_constraints.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py`
- Test: `g:\generative_agents\test\test_decision_constraints.py`

- [ ] **Step 1: 写失败测试，要求最近失败目标从资源列表中剔除**

```python
# g:\generative_agents\test\test_decision_constraints.py
from persona.cognitive_modules.decision_constraints import filter_invalid_resources


def test_filter_invalid_resources_removes_recent_failed_target():
    resources = ["apple tree", "refrigerator", "behind the cafe counter"]
    filtered = filter_invalid_resources(resources, ["apple tree"])

    assert filtered == ["refrigerator", "behind the cafe counter"]
```

- [ ] **Step 2: 实现最小资源过滤器**

```python
# g:\generative_agents\reverie\backend_server\persona\cognitive_modules\decision_constraints.py
def filter_invalid_resources(resources, invalid_targets):
    invalid = {str(item).strip().lower() for item in invalid_targets if str(item).strip()}
    filtered = []
    for item in resources or []:
        text = str(item).strip()
        if text.lower() in invalid:
            continue
        filtered.append(item)
    return filtered
```

- [ ] **Step 3: 在 Prompt 构造前过滤资源**

```python
# g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py
from persona.cognitive_modules.decision_constraints import filter_invalid_resources

nearby_resources = filter_invalid_resources(nearby_resources, invalid_targets)
```

- [ ] **Step 4: 运行测试，确认资源过滤通过**

Run:

```bash
python -m unittest test.test_decision_constraints
```

Expected:

```text
OK
```

- [ ] **Step 5: 提交**

```bash
git add g:\generative_agents\reverie\backend_server\persona\cognitive_modules\decision_constraints.py g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py g:\generative_agents\test\test_decision_constraints.py
git commit -m "feat(prompt): filter invalid targets from resource candidates"
```

---

### Task 3: 增加输出后校验与单次重试，不执行明显违规结果

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\decision_constraints.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py`
- Test: `g:\generative_agents\test\test_decision_constraints.py`
- Test: `g:\generative_agents\test\test_joint_decision_pipeline.py`

- [ ] **Step 1: 写失败测试，要求命中禁选目标时触发单次重试**

```python
# g:\generative_agents\test\test_joint_decision_pipeline.py
def test_invalid_target_triggers_single_retry():
    decision = {"action": "Gather", "target": "apple tree", "detail": "picking apples"}
    invalid_targets = ["apple tree"]

    should_retry, reason = validate_decision_target(decision, invalid_targets)

    assert should_retry is True
    assert "invalid for this step" in reason
```

- [ ] **Step 2: 实现决策目标校验器与重试反馈构造**

```python
# g:\generative_agents\reverie\backend_server\persona\cognitive_modules\decision_constraints.py
def validate_decision_target(decision, invalid_targets):
    target = str((decision or {}).get("target") or "").strip().lower()
    invalid = {str(item).strip().lower() for item in invalid_targets if str(item).strip()}
    if target and target in invalid:
        return True, f"The target {target} is invalid for this step because it just failed and is currently unreachable."
    return False, ""


def build_retry_feedback(reason):
    return reason + " Choose another feasible immediate target or a materially different immediate plan."
```

- [ ] **Step 3: 在 `plan.py` 中增加单次重试，不允许无限循环**

```python
# g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py
should_retry, retry_reason = validate_decision_target(decision, invalid_targets)
if should_retry:
    retry_hint = build_retry_feedback(retry_reason)
    decision = _run_decision_pipeline(..., decision_convergence_hint=retry_hint, allow_retry=False)
```

- [ ] **Step 4: 记录约束命中日志，方便后续评估**

```python
# g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py
append_debug_log(
    "decision_constraint_hits.jsonl",
    {
        "persona": persona.name,
        "step": persona.scratch.curr_step,
        "invalid_targets": invalid_targets,
        "original_decision": decision,
        "retry_reason": retry_reason,
    },
)
```

- [ ] **Step 5: 运行测试，确认单次重试通过**

Run:

```bash
python -m unittest test.test_decision_constraints test.test_joint_decision_pipeline
```

Expected:

```text
OK
```

- [ ] **Step 6: 提交**

```bash
git add g:\generative_agents\reverie\backend_server\persona\cognitive_modules\decision_constraints.py g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py g:\generative_agents\test\test_decision_constraints.py g:\generative_agents\test\test_joint_decision_pipeline.py
git commit -m "feat(plan): add invalid target retry guard"
```

---

### Task 4: 改造决策日志契约，补齐训练准备所需字段

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\persona\prompt_template\gpt_structure.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py`
- Create: `g:\generative_agents\test\test_decision_training_logs.py`
- Modify: `g:\generative_agents\docs\llm_constraint_and_finetune_workflow.md`

- [ ] **Step 1: 写失败测试，固定训练准备日志字段**

```python
# g:\generative_agents\test\test_decision_training_logs.py
import unittest

from persona.training.training_candidate_builder import normalize_training_log_record


class DecisionTrainingLogTests(unittest.TestCase):
    def test_normalize_training_log_record_contains_required_fields(self):
        record = normalize_training_log_record({
            "decision_id": "Isabella-61-abc123",
            "persona": "Isabella Rodriguez",
            "curr_step": 61,
            "prompt_kind": "joint_decision",
            "final_prompt": "Decision Capsule: ...",
            "decision": {"action": "Gather", "target": "apple tree"},
            "execution_outcome": "path_not_found",
        })

        self.assertEqual(
            sorted(record.keys()),
            [
                "curr_step",
                "decision",
                "decision_id",
                "execution_outcome",
                "final_prompt",
                "persona",
                "prompt_kind",
            ],
        )
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```bash
python -m unittest test.test_decision_training_logs
```

Expected:

```text
ERROR: No module named 'persona.training.training_candidate_builder'
```

- [ ] **Step 3: 在请求链路中补齐统一 `decision_id` 与最终 prompt 落盘**

```python
# g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py
decision_id = f"{persona.name}-{persona.scratch.curr_step}-{uuid.uuid4().hex[:8]}"
```

```python
# g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py
append_debug_log(
    "logs/training_dataset/decision_training_prep.jsonl",
    {
        "decision_id": decision_id,
        "persona": persona.name,
        "curr_step": getattr(persona.scratch, "curr_step", None),
        "prompt_kind": "joint_decision",
        "final_prompt": prompt,
        "prompt_hash": prompt_hash,
    },
)
```

- [ ] **Step 4: 记录输出、约束命中与执行结果，统一到同一日志契约**

```python
# g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py
append_debug_log(
    "logs/training_dataset/decision_training_prep.jsonl",
    {
        "decision_id": decision_id,
        "persona": persona.name,
        "curr_step": persona.scratch.curr_step,
        "decision": decision,
        "constraint_hit": should_retry,
        "retry_reason": retry_reason,
        "execution_outcome": execution_outcome,
    },
)
```

- [ ] **Step 5: 在工作流文档中固定日志字段契约**

```markdown
## Decision Training Prep Log Contract

- `decision_id`
- `persona`
- `curr_step`
- `prompt_kind`
- `final_prompt`
- `prompt_hash`
- `decision`
- `constraint_hit`
- `retry_reason`
- `execution_outcome`
```

- [ ] **Step 6: 运行测试，确认通过**

Run:

```bash
python -m unittest test.test_decision_training_logs test.test_joint_decision_pipeline test.test_demand_thinking_memory_context
```

Expected:

```text
OK
```

- [ ] **Step 7: 提交**

```bash
git add g:\generative_agents\reverie\backend_server\persona\prompt_template\gpt_structure.py g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py g:\generative_agents\test\test_decision_training_logs.py g:\generative_agents\docs\llm_constraint_and_finetune_workflow.md
git commit -m "feat(logs): add decision training prep contract"
```

---

### Task 5: 统一日志存储与格式化，确保样本可稳定 join

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\debug_log.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\prompt_template\gpt_structure.py`
- Modify: `g:\generative_agents\docs\llm_constraint_and_finetune_workflow.md`
- Create: `g:\generative_agents\test\check_invalid_target_behavior.py`
- Modify: `g:\generative_agents\test\test_decision_training_logs.py`

- [ ] **Step 1: 写失败测试，要求新日志记录可按 `decision_id` 聚合**

```python
# g:\generative_agents\test\test_decision_training_logs.py
def test_join_key_is_decision_id():
    records = [
        {"decision_id": "abc", "event": "prompt_logged"},
        {"decision_id": "abc", "event": "decision_logged"},
        {"decision_id": "abc", "event": "execution_logged"},
    ]

    assert len({row["decision_id"] for row in records}) == 1
```

- [ ] **Step 2: 统一格式化规则，禁止散乱字段结构**

```markdown
## Log Formatting Rules

- 所有训练准备日志统一写入 `logs/training_dataset/decision_training_prep.jsonl`
- 一行一个事件
- 必带 `decision_id`, `persona`, `curr_step`, `event`, `ts`
- 复杂对象使用 JSON 对象，不拼接自然语言长字符串
```

- [ ] **Step 3: 更新离线检查脚本，按 `decision_id` 统计约束命中与重复失败 target**

```python
# g:\generative_agents\test\check_invalid_target_behavior.py
import json
from collections import defaultdict
from pathlib import Path


def main():
    path = Path("g:/generative_agents/logs/training_dataset/decision_training_prep.jsonl")
    grouped = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        grouped[row["decision_id"]].append(row)
    print(f"decisions={len(grouped)}")
```

- [ ] **Step 4: 运行短模拟与检查脚本**

Run:

```bash
python -m unittest test.test_decision_constraints test.test_decision_training_logs test.test_joint_decision_pipeline test.test_demand_thinking_memory_context
python g:\generative_agents\reverie\backend_server\reverie.py sim_20260702_170929 sim_20260703_constraint_probe 8
python g:\generative_agents\test\check_invalid_target_behavior.py
```

Expected:

```text
OK
decisions=...
```

- [ ] **Step 5: 提交**

```bash
git add g:\generative_agents\reverie\backend_server\persona\cognitive_modules\debug_log.py g:\generative_agents\reverie\backend_server\persona\prompt_template\gpt_structure.py g:\generative_agents\test\check_invalid_target_behavior.py g:\generative_agents\test\test_decision_training_logs.py g:\generative_agents\docs\llm_constraint_and_finetune_workflow.md
git commit -m "feat(logs): normalize decision training prep storage"
```

---

### Task 6: 建立训练候选样本池，而不是直接开训

**Files:**
- Create: `g:\generative_agents\reverie\backend_server\persona\training\training_candidate_builder.py`
- Create: `g:\generative_agents\test\test_training_candidate_builder.py`
- Create: `g:\generative_agents\test\check_extract_training_candidates.py`
- Modify: `g:\generative_agents\docs\llm_constraint_and_finetune_workflow.md`

- [ ] **Step 1: 写失败测试，固定训练候选样本格式**

```python
# g:\generative_agents\test\test_training_candidate_builder.py
import unittest

from persona.training.training_candidate_builder import build_training_candidate


class TrainingCandidateBuilderTests(unittest.TestCase):
    def test_build_training_candidate_contains_review_fields(self):
        record = build_training_candidate(
            decision_id="abc",
            persona="Isabella Rodriguez",
            final_prompt="Decision Capsule: ...",
            rejected_output="Gather apple tree",
            execution_outcome="path_not_found",
        )
        self.assertEqual(
            sorted(record.keys()),
            ["decision_id", "execution_outcome", "final_prompt", "persona", "rejected_output", "review_status"],
        )
```

- [ ] **Step 2: 实现候选样本构造器**

```python
# g:\generative_agents\reverie\backend_server\persona\training\training_candidate_builder.py
def build_training_candidate(decision_id, persona, final_prompt, rejected_output, execution_outcome):
    return {
        "decision_id": decision_id,
        "persona": persona,
        "final_prompt": final_prompt,
        "rejected_output": rejected_output,
        "execution_outcome": execution_outcome,
        "review_status": "pending",
    }


def normalize_training_log_record(record):
    return {
        "decision_id": record["decision_id"],
        "persona": record["persona"],
        "curr_step": record["curr_step"],
        "prompt_kind": record["prompt_kind"],
        "final_prompt": record["final_prompt"],
        "decision": record["decision"],
        "execution_outcome": record["execution_outcome"],
    }
```

- [ ] **Step 3: 编写候选样本抽取脚本**

```python
# g:\generative_agents\test\check_extract_training_candidates.py
from persona.training.training_candidate_builder import build_training_candidate


def main():
    sample = build_training_candidate(
        decision_id="abc",
        persona="Isabella Rodriguez",
        final_prompt="Decision Capsule: NavigationFailure: target=apple tree ...",
        rejected_output="Gather apple tree",
        execution_outcome="path_not_found",
    )
    print(sample["review_status"])
```

- [ ] **Step 4: 运行测试与样本预览**

Run:

```bash
python -m unittest test.test_training_candidate_builder test.test_decision_training_logs
python g:\generative_agents\test\check_extract_training_candidates.py
```

Expected:

```text
OK
pending
```

- [ ] **Step 5: 在工作流文档中明确“候选样本 != 最终训练样本”**

```markdown
## Candidate Pool First

- 先沉淀 `review_status=pending` 的训练候选样本
- 人审或规则审通过后，才能进入最终训练集
- 当前阶段不直接启动 LoRA 训练
```

- [ ] **Step 6: 提交**

```bash
git add g:\generative_agents\reverie\backend_server\persona\training\training_candidate_builder.py g:\generative_agents\test\test_training_candidate_builder.py g:\generative_agents\test\check_extract_training_candidates.py g:\generative_agents\test\test_decision_training_logs.py g:\generative_agents\docs\llm_constraint_and_finetune_workflow.md
git commit -m "feat(training): add candidate pool builder"
```

---

### Task 7: 定义样本充足度与标签完整性门槛，作为微调前置 gate

**Files:**
- Modify: `g:\generative_agents\docs\llm_constraint_and_finetune_workflow.md`
- Create: `g:\generative_agents\test\check_training_readiness.md`

- [ ] **Step 1: 写出 readiness gate，明确当前不直接开训**

```markdown
## Training Readiness Gate

只有同时满足以下条件，才允许进入下一份“模型微调实施计划”：

- 至少 500 条带 `decision_id` 的完整候选样本
- 至少 100 条 `navigation_failure` 纠偏案例
- 至少 100 条 `high inventory + high satiety` 错误案例
- 至少 90% 样本包含 `final_prompt`
- 至少 90% 样本包含 `execution_outcome`
- 至少 80% 样本完成人工或规则审校
```

- [ ] **Step 2: 写出后续计划边界**

```markdown
## Out Of Scope For This Plan

- 本计划不直接训练 LoRA
- 本计划不直接产出最终 SFT / preference 数据集
- 本计划的交付物是：约束层、日志契约、候选样本池、readiness gate
```

- [ ] **Step 3: 运行最终回归检查**

Run:

```bash
python -m unittest test.test_decision_constraints test.test_decision_training_logs test.test_joint_decision_pipeline test.test_demand_thinking_memory_context test.test_training_candidate_builder
```

Expected:

```text
OK
```

- [ ] **Step 4: 提交**

```bash
git add g:\generative_agents\docs\llm_constraint_and_finetune_workflow.md g:\generative_agents\test\check_training_readiness.md
git commit -m "docs(training): add readiness gate before finetuning"
```

---

## Self-Review

- 本计划已按优先级重排：
  - 阶段一：最小输出约束，立即止血。
  - 阶段二：日志字段、存储、格式化改造，建立训练准备契约。
  - 阶段三：候选样本池与 readiness gate，只做微调准备，不直接开训。
- 计划明确把“模型微调”移出本次执行范围，符合“样本足够多、标签足够完整后再动手”的要求。
- 计划没有要求程序直接替 LLM 选择正解，仍然符合“只排除错误项，不接管决策”的原则。
- 所有测试与检查脚本都放在 `test/` 下，并使用 `test_` / `check_` 前缀，符合当前项目规范。

## Execution Handoff

Plan complete and saved to `docs/plans/2026-07-03-constraint-and-finetune-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
