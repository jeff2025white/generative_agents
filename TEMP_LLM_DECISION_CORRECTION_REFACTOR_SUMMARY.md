# LLM 决策纠错与执行闭环改造总结（临时文档）

> 状态：临时工作记录，整理于 2026-07-17。  
> 已推送基线提交：`345c5ae19 fix: add llm decision correction loop`。  
> 本文后半部分记录的实跑后修复目前仍在本地工作区，尚未提交和推送。

## 1. 改造背景

沙盒中的 NPC 会生成物理上不可执行的动作，例如：

- 背包为空时选择 `Consume apple`；
- 对方背包为空时选择向对方请求物品；
- 资源已经耗尽后仍继续选择同一资源；
- 动作描述是“采集苹果”，写入记忆的事件三元组却是 `is / idle`。

本次改造的核心不是让程序替 LLM 选择正确动作，而是建立一条可观测的自主纠错链：

```text
LLM 首次决策
  → 程序只读校验物理可执行性
  → 返回客观失败证据
  → LLM 根据证据重新决策
  → 再次校验
  → 仅在重试预算耗尽后使用安全 fallback
  → 执行动作并记录结果
  → 将结果写入短期状态、经验和记忆
```

这保留了对 LLM 纠错能力的测试价值：程序不删除候选项、不自动替换目标，也不直接给出应该选择的动作。

## 2. 设计原则

### 2.1 校验器只提供证据

校验器可以回答：

- 决策是否可执行；
- 失败原因码，例如 `inventory_missing`、`target_inventory_empty`、`resource_empty`；
- 当前背包、资源状态、观察数量和所需数量等客观证据。

校验器不负责：

- 从 prompt 中过滤无效动作；
- 替 LLM 选择 `Gather`、`Request` 或其他替代动作；
- 将无效输出静默改写成一个“看起来正确”的动作。

### 2.2 fallback 只在预算耗尽后触发

默认允许 LLM 进行一次自主修正。只有所有修正尝试仍然无效时，系统才生成带有 `correction_fallback` 证据的短时 `Idle`，避免执行层崩溃或产生非法状态。

### 2.3 决策、执行和记忆使用同一结构化语义

经过校验和归一的 `skill_id + target` 是动作语义的权威来源。执行前不再调用另一个 LLM 重新猜测动作事件三元组，避免描述、执行命令和记忆相互矛盾。

## 3. 第一阶段：决策纠错链

主要实现位于：

- `reverie/backend_server/persona/cognitive_modules/decision_constraints.py`
- `reverie/backend_server/persona/cognitive_modules/plan.py`
- `reverie/backend_server/persona/cognitive_modules/action_outcomes.py`
- `reverie/backend_server/persona/memory_structures/scratch.py`

完成内容：

1. 对 LLM 决策进行只读物理约束校验。
2. 生成不含替代动作建议的 `VALIDATION_FEEDBACK`。
3. 支持 `evaluation` 和 `production` 两种纠错模式。
4. 支持通过 `LLM_CORRECTION_MAX_RETRIES` 设置重试预算，当前限制为 0～3 次。
5. 记录完整的 `correction_trace`、失败原因、输入决策和证据。
6. 重试耗尽后才生成带证据的安全 fallback。
7. 将执行结果写入 `action_outcome`，计算目标进度、是否需要重规划以及经验价值。

关键日志：

- `logs/decision_constraint_hits.jsonl`
- `logs/decision_correction_trace.jsonl`
- `logs/decision_prompt_trace.jsonl`
- `logs/action_execution_debug.jsonl`
- `logs/action_outcome.jsonl`
- `logs/translation_verify.jsonl`

## 4. 第二阶段：实跑后修复

### 4.1 修正纠错统计

早期实现会在递归重试的内层提前写入 `correction_budget_exhausted`，导致日志显示已经重试，但汇总字段仍是：

```json
{
  "correction_attempts": 0,
  "repeated_invalid": false
}
```

修复后：

- 根据 trace 中的实际 `attempt` 计算重试次数；
- 完整 trace 合并后再写预算耗尽日志；
- 每个决策只写一条最终预算耗尽事件；
- 可以正确识别连续两次相同的无效原因。

相关代码：`plan.py::_summarize_correction_trace()` 和 `plan.py::_append_correction_budget_exhausted_log()`。

### 4.2 修正动作记忆三元组

问题表现：

```text
description = "Klaus Mueller is gathering apples from the apple tree"
predicate   = "is"
object      = "idle"
```

根因是动作已经归一为 `gather` 后，又调用第二个 LLM 将自然语言描述翻译成事件三元组；该调用失败时回退为 `is / idle`。

修复后使用：

```text
(persona.name, normalized_skill_id, normalized_target)
```

例如：

```text
("Klaus Mueller", "gather", "apple tree")
```

未知、无法归一的旧式动作仍可走原有兼容路径。该修复只影响决策后的语义投影，不会过滤或替 LLM 选择动作。

相关代码：`plan.py::build_structured_action_event()`。

### 4.3 让纠错反馈真正进入 joint-decision prompt

在 `sim_20260717_185143` 中发现：校验日志虽然生成了 `inventory_missing` 反馈，但首次请求和重试请求的 prompt hash 完全相同，LLM 也返回完全相同的 `Consume apple`。

根因：`build_decision_capsule()` 接收了 `decision_convergence_hint`，却没有将其加入最终的 `capsule_lines`。

修复后在决策胶囊中显式加入：

```text
DecisionGuidance: <首次决策指导或 VALIDATION_FEEDBACK>
```

新增回归测试保证：

- 重试 prompt 中必须能找到 `inventory_missing`；
- 首次请求和重试请求的 prompt 内容必须不同；
- 两次 prompt 的 SHA-256 hash 必须不同。

相关代码：`run_gpt_prompt.py::build_decision_capsule()`。

### 4.4 修正 `action_outcome.sim_code`

实跑日志中 `action_outcome` 内部的 `sim_code` 为 `null`，导致难以按运行隔离执行结果。

根因是 Scratch 在完成动作时构造了临时 Persona 上下文，而 `sim_code` 实际挂在已关联的真实 Persona 上。

修复后的取值顺序：

1. 当前传入的 `persona.sim_code`；
2. `scratch._persona_ref.sim_code`；
3. `scratch.sim_code`。

相关代码：`action_outcomes.py::build_action_outcome_record()`。

### 4.5 修正 poignancy 与 focal point 的有效响应误判

实跑统计：

- `event_poignancy`：36/36 使用 fail-safe；
- `focal_pt`：2/2 使用 fail-safe；
- `chat_poignancy`：1/1 使用 fail-safe。

模型实际返回的是有效 JSON，例如：

```json
{"output": 3}
```

或：

```json
{"output": ["What happened?", "Why now?"]}
```

中央请求包装器已经将它们解析成整数或列表，但旧校验器仍按字符串调用 `.strip()` 或 `ast.literal_eval()`，因此有效响应被判为无效。

修复后：

- event/thought/chat poignancy 接受解析后的整数、浮点数或包含数字的字符串；
- 分数必须在 1～10 范围内；
- focal point 接受解析后的列表或字符串形式列表；
- 空列表和非法类型仍会被拒绝。

相关代码：

- `run_gpt_prompt.py::_clean_integer_score_response()`
- `run_gpt_prompt.py::_clean_focal_point_response()`

## 5. 实跑观察

### 5.1 `sim_20260717_182657`

- 纠错链已经运行；
- Klaus 选择向空背包 NPC 请求资源，被校验器拒绝；
- LLM 重试后仍然无效，预算耗尽才 fallback；
- 后续 Klaus 能重新规划为 `gather → consume` 并恢复饱食度；
- 暴露了纠错统计错误和动作记忆 `is / idle` 不一致。

### 5.2 `sim_20260717_185143`

- 纠错统计修复生效：`correction_attempts=1`、`repeated_invalid=true`；
- 新写入的 `gather/consume/leisure_use` 事件与动作描述一致；
- 三个 NPC 最终都成功完成采集和进食；
- 共观察到 6 次目标达成；
- 三个 NPC 吃饱后的下一次决策都将 mood 设为主导动机：
  - Isabella 选择在公共休息室沙发放松；
  - Maria 选择在公共休息室放松，之后寻找 Isabella 聊天；
  - Klaus 选择玩游戏机改善心情；
- 暴露了纠错反馈未进入 prompt、outcome 缺少 sim_code、反思类响应误判三个问题。

## 6. 测试与验证

已完成的主要验证：

- 第一阶段关键测试：58 项通过；
- 第一阶段扩展回归：94 项通过；
- 动作三元组与纠错统计针对性测试：14 项通过；
- 对应相关回归：67 项通过；
- 最新三项修复针对性测试：67 项通过；
- 最新更宽相关回归：105 项通过；
- `py_compile` 通过；
- `git diff --check` 通过。

新增或扩展的测试重点覆盖：

- 无效决策重试后才 fallback；
- 重复无效原因统计；
- 预算耗尽日志只写一次；
- 已验证的 gather 事件不经过第二次 LLM 改写；
- 重试反馈出现在最终 prompt；
- 重试 prompt hash 发生变化；
- `action_outcome` 从真实 Persona 引用恢复 `sim_code`；
- poignancy 接受中央包装器解析后的整数；
- focal point 接受中央包装器解析后的列表。

## 7. 当前状态与下一步

当前状态：

- 已推送提交 `345c5ae19` 包含第一阶段纠错链和执行结果闭环；
- 实跑后发现的统计、动作记忆、prompt 反馈、sim_code 和反思解析修复仍在本地；
- 工作区还存在其他与本次任务无关的地图、文档、数据库和认知模块改动，提交时必须只选择本次相关文件，避免覆盖或夹带用户改动。

建议下一步：

1. 再运行一轮新模拟；
2. 确认同一决策的重试 prompt hash 与首次请求不同；
3. 检查是否出现 `correction_resolved`，评估 LLM 真实纠错成功率；
4. 确认 `action_outcome.outcome.sim_code` 不再为 `null`；
5. 确认 event/thought/chat poignancy 与 focal point 不再全量 fail-safe；
6. 验证无误后，仅提交并推送本次相关文件。

## 8. 本次相关文件清单

核心实现：

- `reverie/backend_server/persona/cognitive_modules/decision_constraints.py`
- `reverie/backend_server/persona/cognitive_modules/plan.py`
- `reverie/backend_server/persona/cognitive_modules/action_outcomes.py`
- `reverie/backend_server/persona/memory_structures/scratch.py`
- `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`
- `reverie/backend_server/persona/cognitive_modules/skill_packs/request_skill.py`
- `reverie/backend_server/persona/cognitive_modules/skill_packs/trade_skill.py`

主要测试：

- `test/test_decision_constraints.py`
- `test/test_joint_decision_pipeline.py`
- `test/test_action_outcomes.py`
- `test/test_execution_state_lifecycle.py`
- `test/test_intent_memory_retrieval.py`
- `test/test_request_trade_skills.py`
- `test/test_plan_act_event_guard.py`
- `test/test_legacy_prompt_task_routes.py`

