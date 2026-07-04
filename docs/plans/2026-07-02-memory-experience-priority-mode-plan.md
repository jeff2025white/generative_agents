# Memory Experience-Priority System Design

> 给后续 agent 的说明：本文档只描述“记忆-经验”系统设计、数据结构、主链路和约束，不包含测试计划、基准结果或执行任务拆分。实现或修改该系统时，应优先遵守“保留 LLM 自主决策权，只增强信息供给层”的原则。

**Goal:** 在不削弱 LLM 自主决策权的前提下，为 persona 增加“按当前意图聚焦检索、经验优先供给、按属性恢复方向排序”的记忆系统，让模型在需求决策时能优先看到与当前状态最相关的过往经验。

**Architecture:** 当前系统由 `AssociativeMemory + Scratch + retrieve/new_retrieve + plan + intent_memory + memory_effects` 组成。主链是在 `decide_demand_action()` 进入 `demand_thinking` 之前，根据当前状态推断 `intent_family`，召回并重排高相关经验，压缩成 `intent_memory_summary` 注入 prompt；同时，对新产生的结果性经验在落盘时记录 `attribute_effects`，用于后续按 `satiety/stamina/health/mood` 的恢复方向排序。

**Tech Stack:** Python 3.10, local Ollama via OpenAI-compatible API, JSONL debug logs, persona memory structures (`scratch`, `associative_memory`, `retrieve`, `plan`)

---

## 1. 设计原则

- 不把行为决策硬编码成状态机。
- 不替 LLM 决定“去哪里吃、去哪里休息、先恢复还是先工作”。
- 只增强信息供给层：
  - 当前最相关的记忆焦点是什么
  - 哪些经验和当前状态最相关
  - 哪些经验曾对当前缺失属性产生正向恢复
- 允许经验排序影响 prompt 内容，但不允许经验排序直接绕过 LLM 输出动作。

---

## 2. 记忆系统总览

### 2.1 三层记忆

- `reverie/backend_server/persona/memory_structures/spatial_memory.py`
  - 保存世界、区域、场景、物体的空间结构。
- `reverie/backend_server/persona/memory_structures/associative_memory.py`
  - 保存长期联想记忆。
  - 节点类型包含 `event / thought / chat`。
- `reverie/backend_server/persona/memory_structures/scratch.py`
  - 保存运行时状态和短期工作记忆。
  - 包含当前动作、生理值、社交状态、`last_retrieved_memories` 等。

### 2.2 长期记忆节点结构

`AssociativeMemory` 中的节点当前包含：

- `created`
- `expiration`
- `last_accessed`
- `subject`
- `predicate`
- `object`
- `description`
- `embedding_key`
- `poignancy`
- `keywords`
- `filling`
- `attribute_effects`

其中 `attribute_effects` 是这次“经验系统”扩展的关键字段，固定为四属性映射：

```python
{
    "satiety": 0.0,
    "stamina": 0.0,
    "health": 0.0,
    "mood": 0.0,
}
```

语义如下：

- 正值：该经验曾带来该属性的恢复或提升
- 负值：该经验曾带来该属性的下降或损耗
- `0.0`：未知、无变化或旧记忆未标注

旧记忆兼容规则：

- 若旧节点没有 `attribute_effects`，读取时自动归一化为四项全 `0.0`

---

## 3. 记忆写入设计

### 3.1 既有写入链路

- `perceive.py`
  - 新观察事件写入 `event`
  - 聊天先写 `chat`，再补 `event`
- `plan.py`
  - 长期计划摘要写入 `thought`
- `reflect.py`
  - 检索后形成反思洞察，写入 `thought`
- `converse.py` / `skill_packs/chat_skill.py`
  - 对话与对话理解写入 `thought/event`

### 3.2 结果性经验写入

这次扩展新增了：

- `reverie/backend_server/persona/cognitive_modules/memory_effects.py`

职责：

- 采集动作结算前后的四属性快照
- 计算 `attribute_effects`
- 为结果性经验生成补充关键词
- 将经验以 `event` 形式写入长期记忆

### 3.3 当前已接入属性效果写入的动作

- `consume_skill.py`
- `rest_skill.py`
- `generic_activity_skill.py`
- `singing_skill.py`

这些 skill 在数值结算后会：

1. 记录动作前属性快照
2. 执行动作带来的属性变化
3. 计算 `attribute_effects`
4. 生成一条新的结果性经验记忆
5. 将该经验写入 `AssociativeMemory`

示意：

```python
before = capture_attribute_snapshot(persona)
...  # skill 结算
after = capture_attribute_snapshot(persona)
effects = compute_attribute_effects(before, after)
record_stat_change_experience(persona, description, keywords, effects)
```

---

## 4. 检索系统设计

### 4.1 底层通用召回

底层依然由 `reverie/backend_server/persona/cognitive_modules/retrieve.py` 中的 `new_retrieve()` 提供。

候选来源：

- `seq_event + seq_thought`

底层打分因子：

- `recency`
- `relevance`
- `importance`

默认合成方式：

```python
0.5 * recency + 3 * relevance + 2 * importance
```

再乘以 `scratch` 中的：

- `recency_w`
- `relevance_w`
- `importance_w`

这个阶段的职责是：

- 从全量长期记忆里先召回“可能相关”的候选
- 不处理当前需求的专用偏置

### 4.2 经验优先检索层

专用经验检索层位于：

- `reverie/backend_server/persona/cognitive_modules/intent_memory.py`

主要函数：

- `infer_memory_focus(persona, action_signature=None)`
- `build_intent_focal_points(persona, intent_family, action_signature=None)`
- `retrieve_intent_memories(persona, intent_family, action_signature=None, n_count=5)`
- `summarize_intent_memories(intent_family, retrieved)`

职责：

- 根据当前状态决定“现在应该检索哪类经验”
- 为该类经验生成语义 focal points
- 调用 `new_retrieve()` 获取候选
- 对候选做二次重排
- 将结果压缩成短摘要供给 LLM

---

## 5. 意图族设计

### 5.1 当前支持的意图族

- `restore_satiety`
- `restore_stamina`
- `restore_health`
- `restore_mood`

### 5.2 意图推断优先级

`infer_memory_focus()` 的优先级为：

1. 若当前动作签名中已有 `intent_family`，直接使用
2. 若当前属性跌破阈值，则根据属性缺口推断
3. 若最近完成动作存在强相关意图，可作为补充
4. 否则返回 `None`

当前属性阈值设计：

- `satiety < 50` 倾向 `restore_satiety`
- `stamina < 50` 倾向 `restore_stamina`
- `health < 70` 倾向 `restore_health`
- `mood < 50` 倾向 `restore_mood`

说明：

- `satiety/stamina` 更接近即时生理危机
- `health/mood` 目前也支持经验排序，但仍属于信息供给层增强，不应直接替代动作规划

### 5.3 Focal Points 设计

每个意图族都会生成一组语义化问题，供 `new_retrieve()` 做 embedding 召回。

例如：

- `restore_satiety`
  - 最近成功恢复饱食度的方法
  - 最近与食物相关的结果
  - 附近已知食物来源
  - 上次找食物发生了什么
- `restore_health`
  - 最近成功恢复健康的方法
  - 最近健康恢复结果
  - 哪些行为曾让身体变好或变差
- `restore_mood`
  - 最近成功恢复情绪的方法
  - 哪些活动曾带来安抚、放松、振作

---

## 6. 排序设计

### 6.1 第一层：语义候选召回

先由 `new_retrieve()` 基于 `recency + relevance + importance` 召回候选。

### 6.2 第二层：意图关键词偏置

`intent_memory.py` 会根据 `intent_family` 对候选做二次加权。

例如：

- `restore_satiety`
  - 偏爱 `food / consume / gather / refrigerator / apple / meal / satiety`
- `restore_stamina`
  - 偏爱 `rest / sleep / bed / sofa / stamina`
- `restore_health`
  - 偏爱 `health / heal / treatment / recover`
- `restore_mood`
  - 偏爱 `mood / calm / comfort / music / joy / relax`

### 6.3 第三层：属性效果方向排序

这是“经验系统”相对纯语义检索的核心增量。

当 persona 当前某项属性偏低时：

- 对应属性为正向恢复的记忆获得额外加分
- 对应属性为负向损耗的记忆获得扣分

例如：

- 当前 `health` 很低：
  - `attribute_effects["health"] > 0` 的记忆优先
  - `attribute_effects["health"] < 0` 的记忆后置
- 当前 `mood` 很低：
  - `attribute_effects["mood"] > 0` 的记忆优先
  - `attribute_effects["mood"] < 0` 的记忆后置

本质上，这层不是在决定动作，而是在回答：

- 哪些经验曾真正修复当前最缺的属性
- 哪些经验虽然语义相关，但曾带来反效果

---

## 7. Prompt 注入设计

### 7.1 接线位置

经验优先主链接在：

- `reverie/backend_server/persona/cognitive_modules/plan.py`

具体是在 `decide_demand_action()` 内：

1. 推断 `intent_family`
2. 检索 `intent_memories`
3. 生成 `intent_memory_summary`
4. 将摘要传入 `run_gpt_prompt_demand_thinking(...)`

### 7.2 Prompt 输入结构

`run_gpt_prompt_demand_thinking(...)` 位于：

- `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`

已新增参数：

```python
intent_memory_summary=None
```

模板文件：

- `reverie/backend_server/persona/prompt_template/v2/demand_decision_thinking_v1.txt`

模板中新增了：

```text
Relevant Prior Experience:
!<INPUT 13>!
```

### 7.3 注入方式

这里的设计不是把程序写成一句硬编码结论，例如：

```text
我现在很饿，上次在冰箱吃过，所以这次也去冰箱
```

而是把信息拆成两个区块共同喂给模型：

- 当前状态与生理解释
- 相关经验摘要

例如：

```text
Relevant prior food-related experience:
- Maria Lopez consumed a cooked meal and recovered from hunger quickly.
- Maria Lopez gathered apples from the refrigerator and restored her satiety effectively.
```

LLM 再基于这些信息自行生成自然语言思考。

---

## 8. 日志与可观测性

### 8.1 检索日志

经验优先检索会落盘到：

- `logs/intent_memory_retrieval.jsonl`

记录内容包括：

- `persona`
- `curr_step`
- `intent_family`
- `focal_points`
- `selected_memory_ids`
- `selected_memory_descriptions`
- `attribute_preferences`
- `summary_chars`
- `duration_ms`

### 8.2 其他相关日志

系统其余慢点和 LLM 调用日志仍沿用：

- `logs/step_timing.jsonl`
- `logs/ollama_request_timing.jsonl`

这些日志在设计上属于外围观测层，不改变经验检索主逻辑。

---

## 9. 已落地文件

核心文件如下：

- `reverie/backend_server/persona/cognitive_modules/intent_memory.py`
  - 意图推断、focal points、二次重排、摘要生成
- `reverie/backend_server/persona/cognitive_modules/memory_effects.py`
  - 属性快照、delta 计算、结果性经验写入
- `reverie/backend_server/persona/memory_structures/associative_memory.py`
  - 长期记忆节点结构与 `attribute_effects` 持久化
- `reverie/backend_server/persona/cognitive_modules/plan.py`
  - `decide_demand_action()` 接入经验摘要
- `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`
  - `run_gpt_prompt_demand_thinking(..., intent_memory_summary=None)`
- `reverie/backend_server/persona/prompt_template/v2/demand_decision_thinking_v1.txt`
  - `Relevant Prior Experience` 模板槽位

结果性经验写入当前已接入：

- `reverie/backend_server/persona/cognitive_modules/skill_packs/consume_skill.py`
- `reverie/backend_server/persona/cognitive_modules/skill_packs/rest_skill.py`
- `reverie/backend_server/persona/cognitive_modules/skill_packs/generic_activity_skill.py`
- `reverie/backend_server/persona/cognitive_modules/skill_packs/singing_skill.py`

---

## 10. 边界与约束

- 该系统是“经验供给系统”，不是“动作规则系统”
- 不允许因为某个属性低就直接跳过 LLM 强制落技能
- `attribute_effects` 只描述“过去经验对属性的结果”，不描述“当前一定该做什么”
- 旧记忆大量缺少 `attribute_effects`，因此排序效果会随新经验积累逐步增强
- 经验摘要必须保持短小，避免把 prompt 变成新的性能瓶颈
- 开放语义任务，例如复杂社交，不应被过强的意图偏置误伤

---

## 11. 给后续 Agent 的实现提醒

- 修改经验系统时，优先检查：
  - `intent_memory.py`
  - `memory_effects.py`
  - `associative_memory.py`
  - `plan.py`
  - `run_gpt_prompt.py`
- 若要扩展新的恢复类经验，优先考虑：
  - 是否真的存在稳定的属性结果
  - 是否应该写入 `attribute_effects`
  - 是否需要新增对应 `intent_family`
  - 是否只增强信息供给，而没有替代 LLM 决策
- 若要新增属性相关经验，尽量通过“动作结果写入”而不是“事后硬补描述”
- 若要调整排序，优先改“候选重排权重”，不要直接破坏 `new_retrieve()` 的通用性
