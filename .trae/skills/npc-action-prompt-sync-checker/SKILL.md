---
name: "npc-action-prompt-sync-checker"
description: "Checks whether newly added or modified NPC action skills are fully reflected in prompt static text, parsing, registration, and tests. Invoke after adding/changing any NPC action skill."
---

# NPC Action Prompt Sync Checker

使用这个 Skill，专门检查：

- 一个新的 NPC 动作 skill 已经通过代码实现
- 但它是否已经完整同步到了提示词静态文本、解析映射、执行注册和测试中

这个 Skill 的核心目标是防止出现这种假闭环：

- 执行层已经能跑
- 但 LLM 提示词里不知道这个动作
- 或翻译层不会产出这个类别
- 或解析层不会把它路由到正确 skill_id
- 或 schema 中没有这个 target / verb / category

最终导致“代码里有这个技能，但模型几乎永远不会选它，或者选了也落不到执行层”。

## When To Invoke

在以下场景调用本 Skill：

- 新增了一个 NPC 动作 skill pack 之后
- 修改了一个已有动作 skill 的类别、verb、target 或行为语义之后
- 用户明确要求“检查这个动作有没有同步到提示词静态文本”
- 用户怀疑“代码实现了，但 prompt 里没写，所以模型不会用”
- 用户要求对 NPC 动作的“代码层 -> prompt 层 -> 解析层”做一致性审计

不要在以下场景调用本 Skill：

- 用户只是想看某个 step 的运行日志
- 用户只是想排查某一次执行失败原因
- 用户只是在做普通代码 review，且没有涉及 NPC 动作 skill 的新增/变更

## What This Skill Checks

这个 Skill 不只检查“有没有写进 prompt”，而是检查一整条闭环：

1. **代码实现层**
2. **技能注册层**
3. **动作翻译与归一层**
4. **静态提示词与 schema 层**
5. **测试层**

## Required Inputs

最好具备以下至少一项：

- 新增/修改的 skill 文件路径
- skill 名称
- action category 名称
- 用户给出的 PR / diff / 目标功能描述

如果用户没有明确给出 skill 名称，先从以下目录推断：

- `reverie/backend_server/persona/cognitive_modules/skill_packs/`

## Primary Files To Inspect

优先检查这些文件：

- 技能实现目录：
  - `reverie/backend_server/persona/cognitive_modules/skill_packs/`
- 技能注册表：
  - `reverie/backend_server/persona/cognitive_modules/skill_packs/__init__.py`
- 动作归一与意图归类：
  - `reverie/backend_server/persona/cognitive_modules/action_command_utils.py`
- 解析与 persona-target 路由：
  - `reverie/backend_server/persona/cognitive_modules/plan.py`
- 阶段 2 动作翻译模板：
  - `reverie/backend_server/persona/prompt_template/v2/action_translation_v1.txt`
- 阶段 2 动作 schema：
  - `reverie/backend_server/persona/prompt_template/v2/action_schema.json`
- 阶段 1 / 阶段 2 prompt 相关拼装逻辑：
  - `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`
  - `reverie/backend_server/persona/cognitive_modules/stage1_prompt_compiler.py`
- 相关测试：
  - `test/test_action_mapping.py`
  - `test/test_new_motive_skills.py`
  - `test/test_*skill*.py`

## Required Audit Checklist

每次检查都必须覆盖以下项目。

### 1. 技能实现是否真实存在

确认：

- 是否已经有对应 `skill pack` 文件
- 是否实现了至少这些核心方法
  - `can_execute()`
  - `get_target_tiles()`
  - `on_arrive()`
- 是否有明确的 `self.name`
- 是否在失败路径和成功路径上都能返回可解释结果

如果没有真实 skill pack，只是 schema 写了类别，必须明确指出“只是提示词能力，不是可执行能力”。

### 2. 技能是否已注册

检查：

- `skill_packs/__init__.py` 中是否存在该 skill 的注册项
- 是否补了常见别名
- LLM 可能说出的动词变体是否能命中这个 skill

例如：

- `request / ask / seek`
- `trade / exchange / barter`
- `hangout / linger / loiter`

如果 skill pack 存在但注册表没有，必须标为高优先级缺口。

### 3. 归一映射是否完整

检查：

- `action_command_utils.normalize_skill_id()` 是否能把该动作的 category、verb、detail、target 归一到正确的 `skill_id`
- `infer_intent_family()` 是否给了合理的意图家族
- 是否存在“模型会说，但归一函数接不住”的常见说法遗漏

重点查这几类断点：

- category 已有，但 target/detailed text 不会触发正确归一
- verb 变体没加
- 新 skill 落到了错误的 intent family
- 情绪技能没有被归到 `leisure` 或 `communication`
- 取食技能没有被归到 `restore_satiety`

### 4. persona-target 路由是否完整

如果该动作是“对人动作”，必须检查 `plan.py` 中相关分支是否把它当作 persona-target 技能处理。

重点检查：

- `chat with`
- `seek_and_chat`
- `request`
- `trade`
- `give`
- `rob`
- 以及任何新加入的“对人动作”

如果对人动作没有被纳入 persona-target 路由，模型即使产出正确动作，也可能在解析层掉线。

### 5. 静态提示词文本是否同步

这是本 Skill 最重要的检查项。

必须检查以下两处：

#### A. `action_translation_v1.txt`

确认：

- `action` 可选类别里有没有这个动作类别
- `target` 说明里有没有覆盖这类目标
- 输出 JSON 格式示例里有没有体现这个类别

如果模板还在暗示只能输出旧类别，必须明确指出“LLM 被静态文本限制”。

#### B. `action_schema.json`

确认：

- 是否存在对应 category
- `verbs` 是否覆盖常见表述
- `allowed_targets` 是否包括真实会出现的对象/地点/人
- `description` 是否与执行层真实语义一致
- `actor_delta_amplitude_by_variant` 是否至少有合理的提示性定义

如果 skill 已实现，但 schema 没有对应类别、verb 或 target，必须指出“模型很难稳定选中该动作”。

### 6. 阶段 1 是否能感知这类动作的存在

检查：

- 阶段 1 提示词拼装逻辑是否会把这类可达目标放进上下文
- `stage1_prompt_compiler.py` 中的资源/场所用途文本，是否能让模型理解该技能有什么用
- 如果是新地点、新资源、新社交对象类型，是否已有中文“用途”映射

如果阶段 1 根本不知道某个地点/对象与该 skill 的关系，模型通常不会在自然语言思考阶段想到它。

### 7. 测试是否覆盖

至少检查是否有：

- `normalize_skill_id()` 的归一测试
- `infer_intent_family()` 的归类测试
- skill pack 的基本执行测试
- 如果是对人动作，最好有 persona-target 路由测试

如果没有测试，建议最少补：

- 一个 action mapping 测试
- 一个 skill 执行测试

## Output Contract

输出结果时，优先使用以下结构：

### 1. 结论

直接回答：

- 这个 skill 是否已经形成“代码实现 -> 提示词静态文本 -> 解析层 -> 执行层”的完整闭环

用三档结论之一：

- `已闭环`
- `部分闭环`
- `未闭环`

### 2. 缺口清单

按严重性列出：

- 缺少 skill 注册
- 缺少 normalize 映射
- 缺少 persona-target 路由
- 缺少 `action_translation_v1.txt` 类别声明
- 缺少 `action_schema.json` category / verb / target
- 缺少 stage 1 用途提示
- 缺少测试

### 3. 具体文件定位

必须给出具体文件路径，并尽量指向关键符号或代码块。

### 4. 修复建议

给最小修复面，不要泛泛而谈。

例如：

- “把 `Request` 加进 `action_translation_v1.txt` 的 action enum”
- “把 `pub/bar` 加进 `Recreate.allowed_targets`”
- “在 `normalize_skill_id()` 中补 `barter -> trade`”

## Execution Guidance

如果用户不仅要检查，还要顺手修复，则按以下顺序动手：

1. 先补技能注册
2. 再补归一映射
3. 再补 `action_translation_v1.txt`
4. 再补 `action_schema.json`
5. 再补 `plan.py` 的 persona-target 路由
6. 最后补测试

这样可以保证从“模型会说”到“解析能接”再到“执行能跑”的闭环最稳。

## Good Findings Examples

好的结论应该长这样：

- “`trade_skill.py` 已存在，但 `action_translation_v1.txt` 仍未允许 `Trade` 类别，所以 LLM 静态上仍被限制在旧动作集合。”
- “`hangout_social_venue` 已注册，但 `pub/bar` 没有进入 `Recreate.allowed_targets`，导致模型即使想去酒吧放松，也不容易被 schema 支持。”
- “`request` 已有 skill pack 和注册项，但 `plan.py` 未把它纳入 persona-target 技能分支，因此解析层可能无法把人名目标正确路由。”

## Bad Findings Examples

避免输出这种空泛结论：

- “可能还需要改 prompt”
- “看起来差不多”
- “建议检查一下 schema”

必须把“差在哪里、缺在哪个文件、为什么会影响被选中”说清楚。

## Example Invocation

当用户说：

- “这个新动作虽然写好了，但 prompt 里有没有同步？”
- “帮我检查 request/trade 有没有完整接到提示词”
- “新增 NPC 技能后，写一个一致性检查”
- “为什么代码里有这个 skill，模型还是不用它？”

你应该调用本 Skill，并重点审计：

- `skill_packs/*.py`
- `skill_packs/__init__.py`
- `action_command_utils.py`
- `plan.py`
- `action_translation_v1.txt`
- `action_schema.json`
- 相关测试

## Project-Specific Note

本项目的一个高频坑是：

- 技能代码已存在
- 但 `action_translation_v1.txt` 仍停留在旧类别集合
- 或 `action_schema.json` 漏了新 target / new verb
- 或 `normalize_skill_id()` 没补新说法

所以在这个仓库里，**“动作技能已实现”绝不等于“模型能稳定想到并选中它”**。

本 Skill 的任务就是把这种“伪闭环”显式揪出来。
