# 每步决策提示词说明

本文档整理当前 `g:\generative_agents` 项目中，NPC 在运行过程中“需要重新决策时”实际使用的提示词链路、模板结构、动态变量来源，以及一个贴近真实运行状态的完整示例。

它回答的不是“LLM 为什么会这样想”的抽象问题，而是更工程化的问题：

- 什么时候会重新触发决策
- 真正发给大模型的 Prompt 是什么结构
- 每个字段从哪里来
- 为什么当前系统采用两阶段 Prompt，而不是一步直接输出技能
- 如何从日志中看到真实拼装后的 Prompt

---

## 1. 一句话总结

当前项目的实时决策采用的是一条 **两阶段 Prompt 链路**：

```text
当前状态收集
  -> demand_thinking（自然语言思考）
  -> action_translation（结构化动作翻译）
  -> target/address 解析
  -> add_new_action
  -> execute.py 执行
```

也就是说，系统不会让 LLM 一步直接产出底层技能对象，而是：

1. 先让 LLM 用一句自然语言回答“我现在最该做什么”
2. 再让另一个 Prompt 把这句意图翻译成标准 JSON 动作

这种设计的意义是：

- 保留 LLM 的主观决策空间
- 让“思考”和“执行协议”解耦
- 提高日志可解释性
- 让后续的技能路由、目标归一化、纠偏逻辑更稳定

---

## 2. 什么时候会触发“重新决策”

很多人容易误以为 NPC 每一步移动都会重新问一次 LLM，但当前代码不是这样。

真正触发重新决策的入口在：

- `reverie/backend_server/persona/cognitive_modules/plan.py`
- 函数：`plan()`

关键逻辑是：

```python
if persona.scratch.act_check_finished() or not act_desc:
    if act_desc:
        persona.scratch.last_action_desc = act_desc
    if persona.scratch.should_resume_suspended_action():
        persona.scratch.resume_suspended_action()
        return persona.scratch.act_address
    decide_demand_action(persona, maze)
```

这意味着，只有以下情况才会真正重新做一轮决策：

- 当前动作已经结束
- 当前还没有动作
- 当前动作被挂起，且此时不恢复旧动作而是进入新决策

所以：

- “走路中的每个 path tile” 不一定触发新 Prompt
- 但当 `planned_path` 被消费完、动作完成、或状态切换导致需要重新规划时，就会重新触发

这也是为什么长跑模拟里常见“移动刚结束的那个 step 突然变慢”，因为那一步重新进入了完整的认知链路。

---

## 3. 决策链路总览

真正的实时需求决策函数是：

- `reverie/backend_server/persona/cognitive_modules/plan.py`
- 函数：`decide_demand_action()`

它的大致流程可以概括为：

### 3.1 收集上下文

先整理以下信息：

- 当前可见对象列表 `objs_list`
- 对象微观状态 `object_states`
- 协作/社交事件 `cooperative_events`
- 时间上下文 `temporal_context`
- 生理解释文本 `status_summary`
- 世界规则与当前硬约束 `physiological_rules`
- 最近动作 `last_action_desc`
- 与当前意图相关的经验记忆 `intent_memory_summary`

### 3.2 第一阶段：`demand_thinking`

调用：

- `run_gpt_prompt_demand_thinking()`

输出：

- 一句自然语言意图，例如：

```text
I am severely hungry and my inventory is empty, so I want to gather food from the cafe counter right now.
```

### 3.3 第二阶段：`action_translation`

调用：

- `run_gpt_prompt_action_translation()`

输出：

- 一个结构化 JSON，例如：

```json
{
  "action": "Gather",
  "target": "cafe counter",
  "detail": "getting prepared food from the cafe counter",
  "duration": 10,
  "reasoning": "The intent is to obtain food immediately from a nearby valid food source because hunger is critical and inventory is empty."
}
```

### 3.4 再做程序侧纠偏

得到 JSON 后，代码还会再做一层稳定化处理，例如：

- 若背包为空，但 LLM 选了 `Consume + refrigerator`，会强制改写为 `Gather + refrigerator`
- 若 `Gather` 选了非法食物源，会自动回退到标准食物源
- 会对食物源目标做归一化，例如把别名归一到 `cafe counter`
- 会把动作类别继续归一为内部 `skill_id`

因此，真实执行动作不是“纯 LLM 原样输出”，而是“LLM 决策 + 程序物理约束纠偏”的结合结果。

---

## 4. 第一阶段 Prompt：`demand_thinking`

第一阶段 Prompt 的职责是：

- 让 LLM 看懂当前“人设 + 身体状态 + 环境 + 经验”
- 用一句自然语言说出“我现在最想做的下一步”

实现函数：

- `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`
- 函数：`run_gpt_prompt_demand_thinking()`

模板文件：

- `reverie/backend_server/persona/prompt_template/v2/demand_decision_thinking_v1.txt`

### 4.1 模板骨架

下面是该模板的结构化骨架，已去掉占位符编号说明：

```text
<身份设定 ISS>

Temporal Context:
<当前时间>

Previous Activity Context:
- Last Action: <上一个动作>
Treat the last action only as continuity context...

Current Status:
- Satiety (0-100): <值>
- Stamina (0-100): <值>
- Health (0-100): <值>
- Mood (0-100): <值>
- Inventory: <背包>

Homeostasis Interpretation:
<对四项生理值的主观解释、行为提示、风险说明、Overall Summary>

Homeostasis & World Rules:
<当前世界规则与硬约束>

Nearby Elements & Resources (including Micro-states):
<附近对象及其微观状态>

Cooperative Context / Social Expectations:
<附近协作、等待、社交期望>

Relevant Prior Experience:
<经验记忆摘要>

Decision Convergence Guidance:
<决策收敛提示>

Task: What is the next planned action for <名字> to balance their stats and fulfill their daily role/goals?
Describe what <名字> wants to do next in a simple, natural language sentence...
Answer in one sentence.
```

### 4.2 动态附加指令

除了模板本体外，代码还会在 Prompt 末尾再追加一段动态 `special_instruction`。

这段附加说明会强调：

- 只描述“立即的下一步”
- 只允许提到一个目标对象或地点
- 以 `Homeostasis Interpretation` 作为主要紧迫性依据
- 日程和职业角色是“非强绑定建议”，必要时可以让位给生理需求

当生理值进入危急区时，还会注入强约束，例如：

- `satiety < 30` 且背包为空时，必须表达“先去 Gather 某个有效食物源”
- `satiety < 30` 且背包里有食物时，必须表达“立刻 Consume 背包里的食物”
- `stamina < 30` 时，必须表达“立刻休息/睡觉”

### 4.3 这一阶段的输入字段

代码向这个 Prompt 传入的核心字段包括：

- `identity_summary`
  - 来源：`persona.scratch.get_str_iss()`
  - 含义：身份稳定集，包含名字、性格、职业、背景等

- `satiety/stamina/health/mood`
  - 来源：`persona.scratch`
  - 含义：当前四项核心生理值

- `inventory`
  - 来源：`persona.scratch.inventory`
  - 含义：背包物品

- `nearby_resources`
  - 来源：周边对象树和地图微状态
  - 含义：附近有哪些对象、是否正被使用、是否存在 waiting/served 等事件

- `temporal_context`
  - 来源：`persona.scratch.curr_time`
  - 含义：当前模拟时间

- `status_summary`
  - 来源：`_build_homeostasis_status_summary()`
  - 含义：把数值翻译成主观感受、行为提示与风险

- `rules`
  - 来源：`rules_list`
  - 含义：世界恢复规则、代谢规则、切换成本、危急状态硬约束

- `cooperative_context`
  - 来源：周边事件扫描
  - 含义：附近是否有人等待服务、是否存在协作上下文

- `last_action_desc`
  - 来源：`persona.scratch.last_action_desc`
  - 含义：前一个动作，仅作为连续性参考

- `intent_memory_summary`
  - 来源：`retrieve_intent_memories()` + `summarize_intent_memories()`
  - 含义：与当前意图最相关的经验记忆摘要

- `decision_convergence_guidance`
  - 来源：`build_decision_convergence_hint()`
  - 含义：限制 LLM 不要重新发散规划，而要尽量收敛到“当前最直接下一步”

---

## 5. 第二阶段 Prompt：`action_translation`

第二阶段 Prompt 的职责是：

- 把第一阶段那句自然语言意图，翻译成物理执行层可理解的标准 JSON

实现函数：

- `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`
- 函数：`run_gpt_prompt_action_translation()`

模板文件：

- `reverie/backend_server/persona/prompt_template/v2/action_translation_v1.txt`

### 5.1 模板骨架

```text
You are a precise physical translation engine for a sandbox simulation.

Here is the Action Schema containing the allowed action categories, their allowed target objects, and their descriptions:
<动作 schema>

Here are the interactive targets currently physically near <名字>:
<附近可交互目标>

Now, translate <名字>'s natural language intent:
Intent: "<第一阶段输出>"

Translation Convergence Guidance:
<翻译收敛提示>

Select:
1. "action": Must be one of the standard categories from the Action Schema
2. "target": Must be one of the target objects physically near the agent...
3. "detail": A descriptive action description string
4. "duration": Estimate the duration of the action in minutes
5. "reasoning": A brief explanation of the physical mapping

Respond ONLY in valid JSON format:
{
  "action": "...",
  "target": "...",
  "detail": "...",
  "duration": ...,
  "reasoning": "..."
}
```

### 5.2 为什么需要第二段

如果只让 LLM 输出一句自然语言，那么执行层无法稳定识别：

- 这是 `Gather` 还是 `Consume`
- 目标到底是 `cafe counter` 还是 `cafe customer seating`
- 时长是多少
- 是否应该进入后续技能路由

所以第二段的本质是：

- 第一段负责“认知”
- 第二段负责“协议化”

这就是当前系统里 `demand_thinking -> action_translation` 两步链路存在的根本原因。

### 5.3 动作 Schema

翻译阶段依赖：

- `reverie/backend_server/persona/prompt_template/v2/action_schema.json`

当前定义的宽泛动作类别包括：

- `Consume`
- `Gather`
- `Rest`
- `Work`
- `Socialize`
- `Recreate`

每一类都带有：

- 允许的动词别名
- 类别说明
- 允许目标列表

这一步的目标不是决定最终技能类，而是把自然语言落成一个统一中间协议。

---

## 6. 贴近真实运行的完整示例

下面给出一个贴近当前系统实际运行风格的示例。

### 6.1 假设状态

- NPC：`Klaus Mueller`
- 当前时间：`Tuesday July 02, 2026, 12:10 PM`
- `Satiety = 24.0`
- `Stamina = 62.0`
- `Health = 91.0`
- `Mood = 55.0`
- 背包：空
- 上一个动作：`writing his research paper`
- 附近对象：`refrigerator`, `cafe counter`, `apple tree`, `bed`, `sofa`, `library table`
- 经验记忆：曾有“饥饿且背包空时，优先去标准食物源更直接”的经验

### 6.2 第一阶段 Prompt 示例

```text
Klaus Mueller is a graduate student who is serious, conscientious, and usually focused on research. He values responsibility and tends to follow his work plan, but he also reacts to immediate bodily needs when they become urgent.

Temporal Context:
- Current Time: Tuesday July 02, 2026, 12:10 PM

Previous Activity Context:
- Last Action: writing his research paper
Treat the last action only as continuity context. Do not assume the agent is still tired, hurt, or committed to continuing that activity unless the current stats and Homeostasis Interpretation support it.

Current Status:
- Satiety (0-100): 24.0
- Stamina (0-100): 62.0
- Health (0-100): 91.0
- Mood (0-100): 55.0
- Inventory: empty

Homeostasis Interpretation:
- Satiety Interpretation: severely hungry. Feeling: Your hunger is intense and physically distracting. Behavioral Hint: Getting food should outweigh leisure, exploration, or exercise. Risk: Continuing to ignore food now risks a rapid slide toward physical danger.
- Stamina Interpretation: steady. Feeling: Your body still feels capable and responsive. Behavioral Hint: Work, travel, and active tasks remain reasonable. Risk: Rest is not urgent yet.
- Health Interpretation: feeling healthy. Feeling: Your body feels normal and uninjured. Behavioral Hint: You do not need to prioritize treatment. Risk: Health is stable right now.
- Mood Interpretation: slightly low. Feeling: You feel a little emotionally flat. Behavioral Hint: Pleasant activity or social contact may become more attractive. Risk: If this declines further, motivation may weaken.
Overall Summary: You are still functional overall, but hunger is currently the most pressing need. With Satiety at 24.0, getting food should usually be your next action and should outweigh leisure, exercise, or emotional comfort unless another need is in immediate crisis.

Homeostasis & World Rules:
- CRITICAL HOMEOPATHY RULE: Satiety (24.0) is critically low! Since your inventory is empty, you CANNOT select 'Consume'. You MUST select 'Gather' targeting a valid food source like 'refrigerator', 'stove', 'cafe counter', or 'apple tree' to get food first!
- Consuming food (Consume action) restores +40.0 Satiety and +5.0 Health, and consumes 1 food item from inventory.
- Gathering food (Gather action) from resources (like apple tree, refrigerator, stove, and cafe counter) adds items to inventory.
- Resting (Rest action) restores +40.0 Stamina.
- Socializing (Socialize action) restores +30.0 Mood.
- Switch Cost: Changing tasks/actions in under 15 minutes consumes a high penalty of -5.0 Stamina.
- Survival Privilege: Daily plan requirements and lifestyle guidelines are non-binding recommendations. You are fully authorized and encouraged to leave work, rest, or eat at any time to maintain Satiety and Stamina above 40.0.

Nearby Elements & Resources (including Micro-states):
refrigerator (idle/normal), cafe counter (idle/normal), apple tree (idle/normal), library table (idle/normal), sofa (idle/normal), bed (idle/normal)

Cooperative Context / Social Expectations:
No special cooperative tasks or wait states are active nearby.

Relevant Prior Experience:
When hunger becomes the most urgent pressure and inventory is empty, directly gathering food from an available food source helps recover quickly. Previously, choosing a standard food source reduced delay and avoided indecisive replanning.

Decision Convergence Guidance:
You are not currently committed to an in-progress travel route, so focus on the latest situation and choose the next immediate action. Relevant prior experience has already narrowed the likely good options. Use that experience to converge quickly instead of exploring many broad alternatives.

Task: What is the next planned action for Klaus to balance their stats and fulfill their daily role/goals?
Describe what Klaus wants to do next in a simple, natural language sentence...
Answer in one sentence.
```

这一步可能得到的自然语言输出是：

```text
I am severely hungry and my inventory is empty, so I want to gather food from the cafe counter right now.
```

### 6.3 第二阶段 Prompt 示例

```text
You are a precise physical translation engine for a sandbox simulation.

Here is the Action Schema containing the allowed action categories, their allowed target objects, and their descriptions:
{... action_schema.json ...}

Here are the interactive targets currently physically near Klaus:
refrigerator, cafe counter, apple tree, library table, sofa, bed

Now, translate Klaus's natural language intent:
Intent: "I am severely hungry and my inventory is empty, so I want to gather food from the cafe counter right now."

Translation Convergence Guidance:
Preserve the immediate intent from the natural language thought. Do not expand into a broader alternative plan. Relevant experience already helped narrow the choice, so translate to the most direct schema action instead of exploring many equivalent targets.

Respond ONLY in valid JSON format.
```

这一阶段可能输出：

```json
{
  "action": "Gather",
  "target": "cafe counter",
  "detail": "getting prepared food from the cafe counter",
  "duration": 10,
  "reasoning": "The intent is to obtain food immediately from a nearby valid food source because hunger is critical and inventory is empty."
}
```

---

## 7. 程序侧还会做哪些纠偏

即使第二阶段已经输出 JSON，程序仍然不会完全盲从。

目前至少会做这些稳定化处理：

- `Consume` 但背包为空时，自动改写为 `Gather`
- `Gather` 命中了非法食物源时，自动回退到标准食物源
- 食物目标名称会做标准化归一
- 结合 `action/target/detail` 进一步归一成内部稳定 `skill_id`
- 再做地址解析，把目标映射到可寻路的 `act_address`

因此，实际链路应该理解为：

```text
Prompt 决策
  -> JSON 意图
  -> 程序纠偏
  -> skill 归一
  -> 地址解析
  -> 执行
```

这也是为什么项目可以同时满足两点：

- 不用大量硬编码 if/else 直接替代 LLM 思考
- 又能避免 LLM 因目标歧义而频繁输出不可执行动作

---

## 8. 为什么这个 Prompt 会比较重

当前真正开销最大的，往往不是第二段 `action_translation`，而是第一段 `demand_thinking`。

原因是它把很多上下文都塞进去了：

- 人设身份文本
- 四项生理值及解释
- 世界规则
- 周边资源与对象状态
- 最近动作
- 经验记忆摘要
- 决策收敛提示

这使它具备更强的决策能力，但也会带来：

- Prompt 体积较大
- 本地 Ollama 推理耗时上升
- 内容轻微漂移就可能导致缓存命中率下降

从近期优化经验看，影响性能的关键点主要有：

- 上下文是否过长
- 资源列表是否稳定排序
- 生理解释文本是否变化过于频繁
- 经验记忆摘要是否能有效帮助收敛

---

## 9. 如何观察真实运行时 Prompt

如果想看到运行过程中“真实拼装后的完整 Prompt”，项目已经内置了打印和日志能力。

相关代码在：

- `reverie/backend_server/persona/prompt_template/print_prompt.py`

当开启对应日志开关后，会记录：

- `prompt_template`
- `gpt_param`
- `prompt_input`
- `prompt`
- `output`

也就是说，你可以直接观察：

- 当前到底使用了哪个模板
- 某个 NPC 在某个 step 的 Prompt 输入是什么
- 模板最终被拼成了什么完整文本
- 大模型最终返回了什么

这对于以下工作尤其重要：

- 排查“为什么 NPC 选错动作”
- 分析“为什么这一 step 特别慢”
- 对比 Prompt 优化前后的长度和内容
- 做 A/B 测试验证经验记忆是否真的加速了决策

---

## 10. 真实日志样本对照

这一节专门回答一个更细的问题：

- 日志里的 `prompt_input` 数组到底怎么看
- `prompt_input[0]` 到 `prompt_input[n]` 分别会落到最终 Prompt 的哪一段
- 当你拿到一条 JSONL 日志时，如何快速反推“LLM 当时看到的完整上下文”

### 10.1 日志记录结构

当开启 Prompt 日志后，`print_prompt.py` 会往：

- `logs/agents/<sim_code>/<persona_name>.jsonl`

写入形如下面的 JSONL 记录：

```json
{
  "ts": "2026-07-02T16:45:12.123456+08:00",
  "persona": "Klaus Mueller",
  "step": 184,
  "game_time": "2026-07-02 12:10:00",
  "prompt_template": "persona/prompt_template/v2/demand_decision_thinking_v1.txt",
  "gpt_param": {
    "engine": "local_ollama",
    "temperature": 0
  },
  "prompt_input": [
    "Klaus Mueller is a graduate student who is serious, conscientious, and usually focused on research.",
    "24.0",
    "62.0",
    "91.0",
    "55.0",
    "empty",
    "refrigerator (idle/normal), cafe counter (idle/normal), apple tree (idle/normal), library table (idle/normal), sofa (idle/normal), bed (idle/normal)",
    "- Current Time: Tuesday July 02, 2026, 12:10 PM",
    "- Satiety Interpretation: severely hungry. Feeling: Your hunger is intense and physically distracting. Behavioral Hint: Getting food should outweigh leisure, exploration, or exercise. Risk: Continuing to ignore food now risks a rapid slide toward physical danger.\nOverall Summary: You are still functional overall, but hunger is currently the most pressing need.",
    "- CRITICAL HOMEOPATHY RULE: Satiety (24.0) is critically low! Since your inventory is empty, you CANNOT select 'Consume'. You MUST select 'Gather' targeting a valid food source like 'refrigerator', 'stove', 'cafe counter', or 'apple tree' to get food first!",
    "No special cooperative tasks or wait states are active nearby.",
    "Klaus",
    "writing his research paper",
    "When hunger becomes the most urgent pressure and inventory is empty, directly gathering food from an available food source helps recover quickly.",
    "You are not currently committed to an in-progress travel route, so focus on the latest situation and choose the next immediate action."
  ],
  "prompt": "<完整拼装后的最终 Prompt>",
  "output": "I am severely hungry and my inventory is empty, so I want to gather food from the cafe counter right now."
}
```

这里要特别注意：

- `prompt_input` 是模板变量的原始数组
- `prompt` 是把模板文件和 `prompt_input` 结合后得到的最终文本
- `output` 是大模型对该 Prompt 的直接输出

### 10.2 `demand_thinking` 的 `prompt_input` 映射表

对于模板 `demand_decision_thinking_v1.txt`，`prompt_input` 的索引和含义如下：

| 索引 | 字段名 | 来源 | 最终落在 Prompt 的位置 |
| --- | --- | --- | --- |
| `prompt_input[0]` | `identity_summary` | `persona.scratch.get_str_iss()` | 文档开头的人设身份段 |
| `prompt_input[1]` | `satiety` | `persona.scratch.satiety` | `Current Status` 中的 `Satiety` |
| `prompt_input[2]` | `stamina` | `persona.scratch.stamina` | `Current Status` 中的 `Stamina` |
| `prompt_input[3]` | `health` | `persona.scratch.health` | `Current Status` 中的 `Health` |
| `prompt_input[4]` | `mood` | `persona.scratch.mood` | `Current Status` 中的 `Mood` |
| `prompt_input[5]` | `inventory` | `persona.scratch.inventory` | `Current Status` 中的 `Inventory` |
| `prompt_input[6]` | `nearby_resources` | 对象树与地图微状态 | `Nearby Elements & Resources` |
| `prompt_input[7]` | `temporal_context` | `curr_time` | `Temporal Context` |
| `prompt_input[8]` | `status_summary` | `_build_homeostasis_status_summary()` | `Homeostasis Interpretation` |
| `prompt_input[9]` | `rules` | `rules_list` | `Homeostasis & World Rules` |
| `prompt_input[10]` | `cooperative_context` | 周边协作事件扫描 | `Cooperative Context / Social Expectations` |
| `prompt_input[11]` | `firstname` | `persona.scratch.get_str_firstname()` | `Task` 段落里的人名占位 |
| `prompt_input[12]` | `last_action_desc` | `persona.scratch.last_action_desc` | `Previous Activity Context` |
| `prompt_input[13]` | `intent_memory_summary` | 经验检索摘要 | `Relevant Prior Experience` |
| `prompt_input[14]` | `decision_convergence_guidance` | `build_decision_convergence_hint()` | `Decision Convergence Guidance` |

### 10.3 从日志还原最终 Prompt 的方法

假设你拿到一条日志，只看 `prompt_input`，那么可以按下面方式快速脑补它在最终 Prompt 里的落点：

```text
prompt_input[0]
  -> 放到 Prompt 最开头，作为身份设定

prompt_input[7]
  -> 放到 Temporal Context

prompt_input[12]
  -> 放到 Previous Activity Context 的 Last Action

prompt_input[1..5]
  -> 依次填入 Current Status

prompt_input[8]
  -> 整块填入 Homeostasis Interpretation

prompt_input[9]
  -> 整块填入 Homeostasis & World Rules

prompt_input[6]
  -> 填入 Nearby Elements & Resources

prompt_input[10]
  -> 填入 Cooperative Context / Social Expectations

prompt_input[13]
  -> 填入 Relevant Prior Experience

prompt_input[14]
  -> 填入 Decision Convergence Guidance

prompt_input[11]
  -> 用于替换 Task 段落中的名字占位
```

也就是说，`prompt_input` 不是随便拼的数组，而是严格按照模板占位符顺序组织的。

### 10.4 对照还原示例

以上面的样本为例，日志里最关键的几项可以这样读：

- `prompt_input[1] = "24.0"`
  - 说明当时饱食度已经进入明显危险区
  - 最终会出现在 `Current Status -> Satiety`

- `prompt_input[8]`
  - 不是简单数值，而是已经解释过的“主观感受 + 行为提示 + 风险”
  - 这决定了 LLM 为什么会把“进食”排在高优先级

- `prompt_input[9]`
  - 是代码额外注入的物理规律和强约束
  - 例如“背包空时不能直接 Consume，必须先 Gather”

- `prompt_input[13]`
  - 是经验记忆摘要
  - 它的作用不是替代决策，而是让 LLM 更快收敛

- `prompt_input[14]`
  - 是决策收敛提示
  - 它会明确要求 LLM 只考虑“当前立即下一步”，不要发散成多阶段计划

如果把这些字段和模板拼起来，最终就会得到一整段完整 Prompt，而日志里的 `prompt` 字段就是这个最终结果。

### 10.5 `action_translation` 的日志怎么读

第二阶段 `action_translation` 的 `prompt_input` 更短，也更像协议翻译器：

| 索引 | 字段名 | 含义 | 最终落在 Prompt 的位置 |
| --- | --- | --- | --- |
| `prompt_input[0]` | `thinking_text` | 第一阶段自然语言输出 | `Intent:` 行 |
| `prompt_input[1]` | `schema_str` | 动作 schema JSON 文本 | `Action Schema` 段 |
| `prompt_input[2]` | `res_str` | 附近可交互目标列表 | `interactive targets currently physically near ...` |
| `prompt_input[3]` | `firstname` | 名字 | 模板中的人名占位 |
| `prompt_input[4]` | `decision_convergence_hint` | 翻译收敛提示 | `Translation Convergence Guidance` |

一个典型日志样本大概是：

```json
{
  "prompt_template": "persona/prompt_template/v2/action_translation_v1.txt",
  "prompt_input": [
    "I am severely hungry and my inventory is empty, so I want to gather food from the cafe counter right now.",
    "{... action schema json ...}",
    "refrigerator, cafe counter, apple tree, library table, sofa, bed",
    "Klaus",
    "Preserve the immediate intent from the natural language thought. Do not expand into a broader alternative plan."
  ],
  "output": {
    "action": "Gather",
    "target": "cafe counter",
    "detail": "getting prepared food from the cafe counter",
    "duration": 10,
    "reasoning": "The intent maps directly to obtaining food from a valid nearby food source."
  }
}
```

读这类日志时，最重要的不是 schema 全文，而是看三点：

- 第一阶段自然语言意图是否已经足够清晰
- 可交互目标列表里是否包含正确目标
- 收敛提示是否在强迫模型忠实翻译，而不是二次发散思考

### 10.6 排查问题时看哪几个字段最有用

如果目标是定位“为什么这一步决策错了”，最值得优先看的不是整段 Prompt，而是这几个字段：

- `prompt_template`
  - 先确认走的是哪一个模板

- `prompt_input[8]` 或 `status_summary`
  - 看生理解释是否和真实数值一致

- `prompt_input[9]` 或 `rules`
  - 看危急约束有没有被正确注入

- `prompt_input[6]` 或 `nearby_resources`
  - 看目标对象是否真的出现在上下文里

- `prompt_input[13]` 或 `intent_memory_summary`
  - 看经验记忆是否帮忙收敛，还是引入了错误偏置

- `prompt_input[14]` 或 `decision_convergence_guidance`
  - 看是否过度约束，或者收敛提示不够强

- `output`
  - 看最终回答到底是“想错了”，还是“翻译错了”

### 10.7 当前仓库里的现实情况

这次整理时，我没有在当前 `g:\generative_agents\logs` 下直接检索到现成的 Prompt JSONL 样本。

这通常说明以下两种情况之一：

- 当前工作区还没开启 `ENABLE_AGENT_PROMPT_LOGS`
- 或者日志写入发生在具体模拟目录下，但当前目录里还没有保留对应运行产物

所以本节给出的样本是 **严格按照当前代码中的真实日志结构还原** 的示例，不是凭空虚构字段。

如果后续你开启了日志开关，就可以把这一节里的字段映射表直接套到真实 JSONL 上做排查。

---

## 11. 关键结论

最后用几句话收束：

1. 当前项目的“每一步决策 Prompt”本质上不是一个单 Prompt，而是 `demand_thinking -> action_translation` 两段链路。
2. 真正负责高层认知的是第一段 `demand_thinking`，它也是最重、最关键的一段。
3. 第二段 `action_translation` 的职责不是思考，而是把自然语言落成标准 JSON 协议。
4. 程序并不会无条件相信 LLM 结果，而是会在翻译后做目标归一、食物源纠偏、技能归一和地址解析。
5. 当前系统的设计目标不是“用代码替代 LLM”，而是“让 LLM 负责决定，让程序负责物理约束与执行稳定性”。

---

## 12. 相关代码位置

- 决策主入口：
  - `reverie/backend_server/persona/cognitive_modules/plan.py`
  - `decide_demand_action()`

- 第一阶段 Prompt 组装：
  - `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`
  - `run_gpt_prompt_demand_thinking()`

- 第一阶段模板：
  - `reverie/backend_server/persona/prompt_template/v2/demand_decision_thinking_v1.txt`

- 第二阶段 Prompt 组装：
  - `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`
  - `run_gpt_prompt_action_translation()`

- 第二阶段模板：
  - `reverie/backend_server/persona/prompt_template/v2/action_translation_v1.txt`

- 动作 Schema：
  - `reverie/backend_server/persona/prompt_template/v2/action_schema.json`

- Prompt 打印与落盘：
  - `reverie/backend_server/persona/prompt_template/print_prompt.py`
