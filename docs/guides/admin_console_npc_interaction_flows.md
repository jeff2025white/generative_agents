# Admin Console 与 NPC 交互流程说明

本文档说明通过网页 `admin/造物主` 与 NPC 交互时，两类典型请求的执行链路：

1. 询问型消息：`你叫什么名字？`
2. 指令型消息：`去摘苹果吃`

文档重点覆盖：

- 前端如何分类消息
- 后端如何从 `SimPendingAction` 注入模拟器
- NPC 最终如何回复或执行动作
- 当前实现下的重要行为差异

---

## 1. 总体入口

网页端与 NPC 交互的统一入口是 Django 视图 `admin_console_with_persona()`。

核心流程如下：

1. 前端提交 `sim_code`、`persona_name`、`user_message` 和可选 `conversation_history`。
2. 服务端用 `classify_creator_message()` 将消息分类为：
   - `query`
   - `instruction`
   - `notify`
3. 视图将消息写入 `SimPendingAction`，类型固定为 `action_type="admin_console"`。
4. 前端轮询等待后端模拟器处理该 action，并回填 `reply`。

相关代码：

- [admin_console_with_persona()](/Users/gun/mygame/generative_agents/environment/frontend_server/translator/views.py:1213)
- [classify_creator_message()](/Users/gun/mygame/generative_agents/environment/frontend_server/translator/views.py:1086)

---

## 2. 流程一：询问 NPC “你叫什么名字？”

### 2.1 消息分类

消息如 `你叫什么名字？` 会被识别为 `query`。

原因：

- 文本包含 `什么`
- 或者以 `?` / `？` 结尾

相关代码：

- [QUERY_HINTS 与分类逻辑](/Users/gun/mygame/generative_agents/environment/frontend_server/translator/views.py:1086)

### 2.2 写入待处理队列

前端请求进入 `admin_console_with_persona()` 后，会生成一条待处理记录：

- `action_type="admin_console"`
- `message_mode="query"`
- `content="你叫什么名字？"`

相关代码：

- [写入 SimPendingAction](/Users/gun/mygame/generative_agents/environment/frontend_server/translator/views.py:1249)

### 2.3 后端模拟器拉取并处理

模拟器主循环在每一步中会调用 `/api/get_pending_actions/` 拉取尚未处理的 action。

如果发现：

- `a_type == "admin_console"`
- `message_mode == "query"`

则走管理员查询分支，异步调用 `_run_admin_console_query_job(...)`，最终进入 `handle_admin_console_query(...)`。

相关代码：

- [pending action 注入主循环](/Users/gun/mygame/generative_agents/reverie/backend_server/reverie.py:557)
- [admin_console query 分支](/Users/gun/mygame/generative_agents/reverie/backend_server/reverie.py:577)
- [handle_admin_console_query()](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/cognitive_modules/admin_console.py:204)

### 2.4 LLM 回答时使用的上下文

`handle_admin_console_query()` 会调用 `_run_admin_llm(..., message_mode="query")`，并构造 `creator_query_v1.txt` 提示词。

传入上下文包括：

- `persona.name`
- `self_state`
- `environment`
- `plans`
- `memories`
- `relationships`
- `history`

也就是说，NPC 回答自己的名字时，并不是硬编码输出，而是让 LLM 基于 persona 当前身份上下文回答；其中名字本身直接来自 `persona.name`。

相关代码：

- [query prompt 组装](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/cognitive_modules/admin_console.py:99)
- [LLM 调用](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/cognitive_modules/admin_console.py:126)

### 2.5 返回结果

这一类请求只会返回文本回复：

- 会生成 `reply`
- `next_action` 为空
- 不会改写 NPC 当前动作

因此这条链路的本质是：

`query -> 构造查询上下文 -> LLM 生成回答 -> 回填 reply -> NPC 继续原计划`

---

## 3. 流程二：向 NPC 下达“去摘苹果吃”

### 3.1 消息分类

消息如 `去摘苹果吃` 会被识别为 `instruction`。

原因：

- 文本命中指令关键词，例如 `去`、`请`、`先`、`马上`

相关代码：

- [INSTRUCTION_HINTS 与分类逻辑](/Users/gun/mygame/generative_agents/environment/frontend_server/translator/views.py:1086)

### 3.2 写入待处理队列

与查询一样，这条消息也会先被存成 `SimPendingAction`，但模式为：

- `action_type="admin_console"`
- `message_mode="instruction"`

相关代码：

- [admin_console_with_persona() 写入逻辑](/Users/gun/mygame/generative_agents/environment/frontend_server/translator/views.py:1249)

### 3.3 后端模拟器处理 instruction

主循环拿到这条 action 后，由于它不是 `query`，会直接调用：

- `handle_admin_console_action(...)`
- 然后进入 `handle_admin_console_instruction(...)`

这条路径不会走普通 NPC 聊天技能包，不会先展开一段“和造物主对话再决定是否执行”的社交式流程。

相关代码：

- [instruction 分支](/Users/gun/mygame/generative_agents/reverie/backend_server/reverie.py:590)
- [handle_admin_console_instruction()](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/cognitive_modules/admin_console.py:236)

### 3.4 指令标准化

`handle_admin_console_instruction()` 先调用 `_normalize_admin_instruction_text(content)`。

对于 `去摘苹果吃`：

- 前缀 `去` 会被移除
- 剩余文本变成 `摘苹果吃`

相关代码：

- [指令标准化](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/cognitive_modules/admin_console.py:56)

### 3.5 写入管理员 override 并打断当前动作

当前实现下，`handle_admin_console_instruction()` 不再直接写入一个旁路动作。

它会做两件事：

1. 将标准化后的指令文本写入 `scratch.admin_override_intent`
2. 如果 NPC 当前有执行中的计划，则调用 `interrupt_execution("admin_console_override")`

这意味着管理员指令的特权只体现在：

- 可以强制打断当前动作
- 可以让下一轮规划优先服从外部指令

但它不会再绕过规划层直接构造 `act_command`。

### 3.6 下一轮进入正常规划层

`plan()` 在发现：

- 当前动作已结束
- 或当前动作被中断后没有 active plan

就会像普通决策一样进入 `decide_demand_action()`。

不同的是，这一轮会先检查是否存在 `admin_override_intent`：

- 若存在，则把它注入决策上下文
- 并暂时跳过 `resume_suspended_action()`

这样管理员指令会优先于“恢复被挂起的旧计划”。

### 3.7 指令如何进入 LLM 决策

在 `decide_demand_action()` 中，管理员 override 会被当作一条最高优先级的外部意图注入到现有 decision pipeline。

这条指令会进入：

- `run_gpt_prompt_demand_thinking(...)`
- `run_gpt_prompt_joint_decision(...)`
- `run_gpt_prompt_action_translation(...)`

对应的 prompt 会明确告诉模型：

- 管理员刚刚下达了哪条指令
- 当前应优先将它翻译成最近的有效 schema action
- 只有遇到硬物理约束时才允许退化处理

### 3.8 为什么这条链路更一致

现在管理员指令不再走：

- `execute -> use`
- `GenericActivitySkillPack`

这种旁路逻辑。

而是和普通自主决策共用同一套主流程：

`管理员指令 -> override intent -> 打断当前动作 -> demand thinking -> action translation -> skill 归一化 -> target resolution -> execute`

这样做的结果是：

- 指令和普通决策复用同一套动作翻译逻辑
- `gather / consume / rest / chat` 等技能不需要在 admin 通道里重复维护一套映射
- 失败重试、资源校验、技能包结算、日志记录全部自动复用

### 3.9 当前实现下的预期效果

以 `去摘苹果吃` 为例，新的预期行为是：

1. 管理员指令进入 override intent
2. NPC 当前动作被中断
3. 下一轮规划时，LLM 会把“摘苹果吃”翻译成最接近的有效 schema action
4. 如果模型翻译为 `Gather -> apple tree`，后续就会自然进入现有的 `GatherSkillPack`
5. 若饱食度较低，`GatherSkillPack` 还会自动安排后续 `Consume -> apple`

因此这条链路的目标形态是：

`instruction -> override intent -> replan -> gather apple tree -> inventory + apple -> consume apple`

---

## 4. 系统中“正确的摘苹果吃”链路其实已经存在

项目内部已经有完整的 `gather -> consume` 生存链路，当前管理员指令的新设计正是为了复用它。

### 4.1 Gather 成功时会加库存

如果技能真的是 `gather`，并且目标是 `apple tree`，`GatherSkillPack.on_arrive()` 会：

- `inventory["apple"] += 2`
- 轻微提升 mood

相关代码：

- [apple tree gather 结算](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/cognitive_modules/skill_packs/gather_skill.py:307)

### 4.2 饱食度低时会自动继续 consume

在 gather 成功后，如果：

- `satiety < 40`
- 且背包里已有 `apple`

系统会自动再排一个新动作：

- `consume apple`

相关代码：

- [gather 后自动排 consume](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/cognitive_modules/skill_packs/gather_skill.py:352)

所以从能力上讲，系统已经支持“先摘苹果，再吃苹果”，管理员指令现在也会通过统一规划链路去争取落成这个技能序列。

---

## 5. 两条流程的对比总结

| 场景 | 消息类型 | 是否调用 LLM 回复 | 是否改写当前动作 | 最终效果 |
| :--- | :--- | :--- | :--- | :--- |
| `你叫什么名字？` | `query` | 是 | 否 | NPC 返回文本回答，继续原计划 |
| `去摘苹果吃` | `instruction` | 是（通过规划层） | 是 | NPC 当前动作被打断，下一轮规划优先执行该指令，并走统一动作翻译链路 |

---

## 6. 当前实现结论

### 6.1 询问类消息

询问 `你叫什么名字？` 这一类消息的链路是稳定的：

- 正确分类为 `query`
- 进入管理员查询上下文
- 使用 `persona.name` 等上下文生成回复
- 不打断当前行为

### 6.2 指令类消息

指令 `去摘苹果吃` 的链路现在已经改为“高优先级外部意图 -> 统一规划翻译”模式。

也就是说：

- 管理员指令仍然可以打断当前动作
- 但不再绕过主规划层
- 最终动作仍由现有 LLM 决策与 schema translation 产出

这使管理员指令执行和普通 NPC 决策保持一致，也降低了额外维护一套 admin 专用执行协议的复杂度。

---

## 7. 建议的后续修复方向

如果后续要让管理员指令真正驱动可执行技能，推荐改成以下策略之一：

1. 在 `admin_console.py` 中直接把“摘苹果/采摘/harvest”映射为 `gather`，而不是统一写成 `execute`。
2. 对“摘苹果吃”这类复合指令拆成两段：
   - 第一段 `gather("apple tree")`
   - 第二段由 `GatherSkillPack` 自动触发 `consume("apple")`
3. 或者引入一个更明确的“管理员动作翻译层”，把自然语言指令先翻译成内部动作协议，再写入 `add_new_action()`。

这会让管理员指令链路与现有技能系统保持一致，也能复用库存、资源扣减和自动进食的既有逻辑。
