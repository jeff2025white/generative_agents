---
name: "full-reasoning-step-report"
description: "Generates a markdown report for one full-reasoning simulation step from run-scoped logs. Invoke when the user asks for a complete single-step reasoning chain report."
---

# Full Reasoning Step Report

使用这个 Skill，把新的 run-scoped 日志系统中的某一个 `sim_code + persona + step` 整理成一份可读的 Markdown 报告，专门用于回答：

- “把某个 step 的全量推理链整理出来”
- “给我一份单个 step 的完整日志报告”
- “按新日志系统输出一个 full reasoning step 报告”
- “把这个 step 的感知 -> 决策 -> 翻译 -> 执行 链条写成文档”

这个 Skill 的目标不是只返回 JSON 聚合结果，而是要生成一份人能直接阅读和复用的“单步链路报告”。

## When To Invoke

在以下场景调用本 Skill：

- 用户明确要“单个 step 的完整日志报告”
- 用户要“整理成文档 / markdown / 报告”
- 用户要“一个 full pipeline step 的完整链条”
- 用户要“以新日志系统为基础，输出一步的完整推理过程”

不要在以下场景调用本 Skill：

- 用户只是要快速看某一步有没有缺阶段
- 用户只是要临时看 JSON 聚合结果
- 用户只想定位某个失败原因，而不需要文档化报告

上述场景优先使用现有的 `step-persona-trace-reader`。

## Required Inputs

必须具备：

- `sim_code`
- `persona`
- `step`

可选：

- `project_root`
- `output_path`

如果用户没有明确给出三元组，先帮助用户从日志中挑选一个合适样本，再继续生成报告。

## Data Contract

本 Skill 仅基于新的 hardened logging schema 工作。目标日志应尽量包含：

- `sim_code`
- `curr_step`
- `sim_time`
- `persona`

主要日志来源：

- `logs/perception_debug.jsonl`
- `logs/intent_memory_retrieval.jsonl`
- `logs/decision_prompt_trace.jsonl`
- `logs/translation_verify.jsonl`
- `logs/decision_stability.jsonl`
- `logs/action_execution_debug.jsonl`
- `logs/action_outcome.jsonl`
- `logs/motive_monitor.jsonl`
- `logs/step_timing.jsonl`

## Implementation Entry

优先复用已有读取器：

- `reverie/backend_server/persona/log_analysis/step_persona_trace_reader.py`

基础命令：

```bash
python3 reverie/backend_server/persona/log_analysis/step_persona_trace_reader.py \
  --sim-code sim_20260710_171736 \
  --persona "Maria Lopez" \
  --step 0
```

## Workflow

### 1. 先确认这个 step 是否值得做“完整报告”

优先选择满足以下条件的 step：

- `step_timing.persona_move_timing.mode = full_pipeline`
- 存在 `decision_prompt_trace` 中的 `demand_thinking`
- 存在 `action_translation`
- 存在 `translation_verify`
- 存在 `action_execution_debug`

如果只是 fast path，不要误称为“全量推理 step”。

### 2. 读取聚合结果

使用 `step_persona_trace_reader.py` 先生成聚合 JSON，重点关注：

- `timeline`
- `grouped`
- `decision_summary`
- `action_outcome_summary`
- `missing_stages`
- `schema_incomplete`

### 3. 补读关键原始日志

如果聚合结果不够解释链路，需要回读原始日志补充：

- `motive_monitor.jsonl`：补主次动机和压力分
- `decision_prompt_trace.jsonl`：补 thought / translation / final_decision
- `translation_verify.jsonl`：补纠偏和目标解析
- `action_execution_debug.jsonl`：补执行事件
- `action_outcome.jsonl`：补结果或说明其缺失原因
- `step_timing.jsonl`：补 full_pipeline / slow path / timing

### 4. 生成 Markdown 报告

默认输出为 Markdown 文件，建议路径：

```text
logs/reports/full_reasoning_step_<sim_code>_<persona_slug>_<step>.md
```

如果用户没有指定输出位置，也可以直接写到：

```text
logs/full_reasoning_step_<sim_code>_<persona_slug>_<step>.md
```

### 5. 明确区分三种情况

报告中必须明确说明该 step 属于哪一种：

1. `全量推理 step`
2. `fast path step`
3. `推理完整但 outcome 未在同一步完成的 step`

不要把“没有 action_outcome”的 step 误写成“链条不完整”，除非证据明确表明它应该在同一步完成。

## Required Report Structure

输出报告时，至少包含以下章节：

### 1. 样本信息

- `sim_code`
- `persona`
- `step`
- 选择该样本的原因

### 2. 核心结论

用 5 到 10 行概括：

- 这一步真正发生了什么
- 主驱动力是什么
- LLM 原始想法是什么
- 翻译层有没有纠偏
- 执行层最终做了什么
- 是否有 outcome

### 3. 单步完整链条

按时间顺序组织，通常包括：

1. 动机背景
2. 感知
3. 意图记忆检索
4. 阶段 1 自然语言思考
5. 阶段 2 动作翻译
6. 翻译校验与纠偏
7. 目标解析
8. 执行落地
9. timing 汇总
10. action outcome 或缺失说明

### 4. 阶段 1 与阶段 2 提示词

如果该 step 存在完整的阶段 1、2 提示词，报告中必须单独整理：

- `Stage 1 Prompt (English Original)`
- `Stage 1 Prompt (中文翻译)`
- `Stage 1 Response`
- `Stage 2 Prompt (English Original)`
- `Stage 2 Prompt (中文翻译)`
- `Stage 2 Response`

提示词原文主要来自：

- `decision_prompt_trace.jsonl`
- `event = prompt_response`
- `prompt_kind = demand_thinking` 对应阶段 1
- `prompt_kind = action_translation` 对应阶段 2

翻译要求：

- 以 `final_prompt` 作为翻译对象，不要自己重构提示词。
- 忠实翻译，不要缩写，不要改写逻辑约束。
- 保留关键字段名、JSON 键名、路径、变量名、命令、代码块与英文标识符原样不动。
- 对自然语言指令、规则说明、背景描述、任务要求等部分翻译成中文。
- 如果提示词过长，可以在正文展示“完整原文 + 完整中文翻译”，不要只给摘要。

### 5. 为什么这是一个 full reasoning step

必须明确给证据，不要凭感觉判断。

### 6. 缺口与注意事项

必须说明：

- `missing_stages`
- `schema_incomplete`
- 是否存在旧 schema / 不完整字段
- 是否存在 `action_outcome` 缺 `sim_code` 等 run-scoped 问题

### 7. 后续可复用模板

给出后续复用方式，例如：

```bash
python3 reverie/backend_server/persona/log_analysis/step_persona_trace_reader.py \
  --sim-code <sim_code> \
  --persona "<persona>" \
  --step <step>
```

并说明如何用相同模板整理别的 step。

## Writing Guidance

生成报告时遵循以下规则：

1. 以“真实日志证据”为主，不要脑补缺失阶段。
2. 明确区分：
   - `llm 原始输出`
   - `translation 初始结果`
   - `decision_routed_*`
   - `execution 最终落地`
3. 如果 `translation_verify` 对动作做了纠偏，必须把“原始动作”和“纠偏后动作”并列写清楚。
4. 如果 `action_outcome` 缺失，必须说明是：
   - 同一步尚未完成动作
   - 还是日志 schema 仍不完整
5. 报告应该是面向开发排查，不是面向终端用户叙事。
6. 当用户要求查看提示词时，优先同时给出：
   - 英文原始提示词
   - 中文翻译提示词
   - 对应阶段输出
7. 中文翻译必须忠实，不要把 prompt 中的硬约束翻成更弱的意思。
8. 对于非常长的提示词，不得只翻译开头；应覆盖完整 `final_prompt`。

## Output Style

使用中文写报告正文，保留必要的英文原始字段名和原始日志内容。

建议保留：

- JSON 片段
- thought 原文
- routed action
- 关键 reason 字段
- timing 数值
- 阶段 1、2 提示词英文原文
- 阶段 1、2 提示词中文翻译

## Good Output Characteristics

一份好的报告应该做到：

- 读者不用重新翻所有 JSONL 文件也能理解该步链路
- 能一眼看出哪一层修正了上一层
- 能区分“逻辑问题”和“schema 问题”
- 能作为后续审计其它 step 的模板

## Example Use

当用户说：

- “把 Maria 这一步整理成完整日志报告”
- “以新的日志系统为基础，输出一个单步全量推理报告”
- “给我一个可以沉淀到文档里的 step 级报告”

你应该：

1. 确认 `sim_code + persona + step`
2. 跑 `step_persona_trace_reader.py`
3. 回补关键原始日志
4. 生成 Markdown 报告
5. 明确说明是否是 `full_pipeline`

## Existing Reference

本项目中已有一个参考样本，可作为报告风格模板：

- `logs/full_reasoning_step_chain.md`

如果生成新报告，优先保持与该文档相同的结构和术语风格。
