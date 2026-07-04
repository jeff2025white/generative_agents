# 大模型自然语言如何落成 Skill 执行

本文档专门说明当前 `g:\generative_agents` 项目里，一条由大模型返回的自然语言意图，是如何一步步变成可执行 `skill` 的。

它回答的不是“LLM 为什么这么想”，而是更工程化的问题：

- 大模型先输出了什么
- 代码如何把自然语言变成结构化命令
- 结构化命令如何被保存
- 执行层如何路由到 `Skill Pack`
- 到达目标后如何真正完成物理结算

---

## 1. 一句话总结

当前项目采用的是一条 **两阶段认知 + 结构化命令 + 技能分发** 的链路：

```text
自然语言思考
  -> 结构化动作 JSON
  -> skill_id 归一化
  -> act_command
  -> act_address / 路径规划
  -> execute.py 查表
  -> Skill Pack.can_execute()
  -> Skill Pack.on_arrive()
```

也就是说，**大模型并不是直接返回一个 Python 技能对象，也不是直接调用技能函数**。  
它先返回自然语言意图和结构化动作描述，系统再把这些结果翻译成内部统一协议 `act_command`，最后由执行层把它分发给具体技能包。

---

## 2. 整体分层

当前链路可以分为 4 层：

### 2.1 认知层：LLM 先想“我要做什么”

认知层负责生成自然语言意图，例如：

```text
我现在有点饿，背包里没有食物，应该去冰箱找点吃的。
```

这一层对应：

- `reverie/backend_server/persona/cognitive_modules/plan.py`
- `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`

### 2.2 翻译层：把意图转成结构化动作

翻译层不会直接执行技能，而是把自然语言转成统一 JSON，例如：

```json
{
  "action": "Gather",
  "target": "refrigerator",
  "detail": "opening the refrigerator to gather food items",
  "duration": 10,
  "reasoning": "Inventory is empty and satiety is low."
}
```

### 2.3 命令层：把宽泛动作收敛为内部 skill_id

项目不会直接拿 `"Gather"` 或 `"Recreate"` 执行，而是继续收敛成内部技能协议：

```json
{
  "skill_id": "gather",
  "target": "refrigerator",
  "source": "decision_translation",
  "raw_action": "Gather",
  "detail": "opening the refrigerator to gather food items"
}
```

这就是 `act_command`。

### 2.4 执行层：按 skill_id 分发到 Skill Pack

执行层读取 `act_command.skill_id`，然后去 `SKILL_REGISTRY` 查找对应技能包，例如：

- `gather -> GatherSkillPack`
- `consume -> ConsumeSkillPack`
- `rest -> RestSkillPack`
- `study -> GenericActivitySkillPack`
- `chat with -> ChatSkillPack`

---

## 3. 详细时序

下面按真实代码的顺序展开。

## 3.1 第一步：LLM 先输出自然语言意图

入口函数是：

- `decide_demand_action()`  
  文件：`reverie/backend_server/persona/cognitive_modules/plan.py`

它先调用：

- `run_gpt_prompt_demand_thinking()`  
  文件：`reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`

这一步的目标不是立刻得到技能名，而是先得到一段“像人脑思考一样”的自然语言意图。

典型形式：

```text
I am hungry and do not have food in my inventory, so I should get food from the refrigerator.
```

这一步的意义是：

- 让 LLM 先做高层决策，而不是过早绑定底层技能
- 保留“思考”和“执行命令”之间的缓冲层
- 为日志和调试提供更强的可解释性

---

## 3.2 第二步：把自然语言意图翻译成结构化 JSON

在得到自然语言意图后，`decide_demand_action()` 会继续调用：

- `run_gpt_prompt_action_translation()`

它使用的 Prompt 模板是：

- `reverie/backend_server/persona/prompt_template/v2/action_translation_v1.txt`

这个 Prompt 明确要求 LLM 只能输出以下字段：

- `action`
- `target`
- `detail`
- `duration`
- `reasoning`

这里的核心思想是：

- `action` 是**宽泛动作类别**
- `target` 是**目标对象/人物**
- `detail` 是**给人看的动作描述**
- `duration` 是**动作时长**
- `reasoning` 是**调试说明**

注意：这一步的 `action` 还不是最终要执行的 `skill_id`。

例如：

```json
{
  "action": "Recreate",
  "target": "piano",
  "detail": "singing at the piano to relax",
  "duration": 20,
  "reasoning": "Mood is low and piano is a suitable leisure activity."
}
```

此时系统还不能直接执行，因为：

- `Recreate` 太宽泛
- 它可能对应 `sing`
- 也可能对应 `rest`
- 也可能对应 `chat with`
- 也可能只是通用 `leisure_use`

---

## 3.3 第三步：把宽泛 action 归一为稳定 skill_id

结构化 JSON 生成后，代码会调用：

- `normalize_skill_id(raw_action, target=None, detail=None)`  
  文件：`reverie/backend_server/persona/cognitive_modules/action_command_utils.py`

这是整个“自然语言落成技能”的核心转换器。

它做两件事：

### 3.3.1 动作别名归一

例如：

- `eat / drink / have / snack -> consume`
- `get / take / search / open -> gather`
- `sleep / idle / relax -> rest`
- `chat / talk / socialize -> chat with`
- `execute -> use`

### 3.3.2 结合 target/detail 进行语义细化

这是最近这轮架构改造里最关键的一步。

例如：

- `Recreate + piano/music/singing -> sing`
- `Recreate + sofa/bed/nap/rest -> rest`
- `Recreate + chatting with Maria -> chat with`
- `Recreate + TV/game console -> leisure_use`
- `Work + bookshelf/blackboard/library table/read/write -> study`
- `Work + coffee maker/counter/cashier/job duty -> work`
- `Work/Use + fitness machine/game console/tv -> use`

也就是说，**最终执行 skill 的不是原始动作词，而是归一化之后的 `skill_id`**。

这一步直接决定：

- 执行层能不能命中技能包
- 会不会出现 `skill_missing`
- 会不会把“宽泛自然语言”稳定落到具体行为

---

## 3.4 第四步：构造 act_command

有了 `skill_id` 之后，系统会调用：

- `build_action_command(skill_id=None, target=None, source="unknown", raw_action=None, detail=None)`

生成统一协议对象：

```json
{
  "skill_id": "sing",
  "target": "piano",
  "source": "decision_translation",
  "raw_action": "Recreate",
  "detail": "singing at the piano to relax"
}
```

这里每个字段的意义如下：

- `skill_id`
  - 内部真正执行的技能标识
  - 执行层只认这个字段

- `target`
  - 技能对应的对象、地点或人物
  - 例如 `refrigerator`、`apple`、`Klaus Mueller`

- `source`
  - 命令来源
  - 例如 `decision_translation`、`survival_direct`、`chat_followup`

- `raw_action`
  - LLM 原始动作类别
  - 例如 `Gather`、`Recreate`、`Work`

- `detail`
  - 供显示与调试使用的自然语言说明

这一步的重要性在于：  
**项目从这里开始，不再依赖不稳定的 event triple 作为唯一执行依据。**

---

## 3.5 第五步：目标解析，把 target 变成 act_address

有了 `act_command` 还不够，因为执行层需要一个可寻路的地址。

因此 `plan.py` 还会继续做目标地址解析：

- 先尝试 `resolve_known_object_address()`
- 再尝试 `resolve_known_arena_address()`
- 最后才退回老的 prompt 解析逻辑

对应文件：

- `reverie/backend_server/persona/cognitive_modules/action_target_resolver.py`
- `reverie/backend_server/persona/cognitive_modules/plan.py`

这个阶段负责把：

```text
target = "piano"
```

转成：

```text
the Ville:Some Sector:some arena:piano
```

或者把：

```text
target = "Maria Lopez"
skill_id = "chat with"
```

转成：

```text
<persona> Maria Lopez
```

最近这部分之所以被加强，是因为过去如果地址解析过松，就会出现：

- `fitness machine` 被解析到 `closet`
- 被解析到 `pool table`
- 被解析到 `customer seating`

现在的策略是：

- 对于已知对象，优先精确命中对象地址
- 对于 `use/work/study/leisure_use` 这类非生存动作，必要时只退回到 **arena 级地址**
- 尽量避免再调用泛化对象选择，把动作漂移到错误物体

---

## 3.6 第六步：把 act_command 写入 Scratch

最终，`plan.py` 会调用：

- `persona.scratch.add_new_action(...)`

把一整套当前动作状态写入 `Scratch`：

- `act_address`
- `act_duration`
- `act_description`
- `act_pronunciatio`
- `act_event`
- `act_command`

其中最关键的是：

```python
self.act_command = action_command or infer_action_command_from_event(...)
```

这意味着：

- 优先使用已经生成好的结构化 `act_command`
- 只有缺失时才回退到从 `act_event` 猜测

也就是说，在当前架构里：

- `act_event` 更偏向记忆/展示/兼容层
- `act_command` 才是执行层更稳定的结构化动作协议

---

## 3.7 第七步：执行层读取 act_command

执行入口在：

- `reverie/backend_server/persona/cognitive_modules/execute.py`

`execute()` 的流程是：

1. 根据 `act_address` 做寻路
2. 每一步推进一个 tile
3. 当 `planned_path` 为空并且 `act_path_set=True` 时，视为“到达目标”
4. 到达后读取 `act_command`

关键逻辑是：

```python
act_command = persona.scratch.act_command or infer_action_command_from_event(...)
action = act_command.get("skill_id", "")
target = act_command.get("target", "")
skill = SKILL_REGISTRY.get(action.lower()) if action else None
```

这里有几个关键点：

- 执行层并不再直接信任自然语言
- 执行层也不再直接依赖原始 `action`
- 它真正依赖的是 `act_command.skill_id`

所以真正的路由关系是：

```text
LLM 自然语言
  -> action
  -> skill_id
  -> SKILL_REGISTRY[skill_id]
```

---

## 3.8 第八步：命中 Skill Registry

技能注册中心在：

- `reverie/backend_server/persona/cognitive_modules/skill_packs/__init__.py`

它定义了：

```python
SKILL_REGISTRY = {
    "consume": ConsumeSkillPack(),
    "gather": GatherSkillPack(),
    "rest": RestSkillPack(),
    "sing": SingingSkillPack(),
    "use": GenericActivitySkillPack(...),
    "work": GenericActivitySkillPack(...),
    "study": GenericActivitySkillPack(...),
    "leisure_use": GenericActivitySkillPack(...),
    "chat with": ChatSkillPack(),
}
```

这一步说明：

- `skill_id` 只是字符串
- 真正的执行逻辑在对应 `Skill Pack` 类里
- 想扩展新动作，本质上是新增 `skill_id + skill pack + registry 注册`

---

## 3.9 第九步：Skill Pack 做物理前置校验

当执行层查到技能包后，先调用：

- `skill.can_execute(persona, target, maze)`

这一步负责判断当前动作是否满足物理前置条件。

例如：

- `ConsumeSkillPack.can_execute()`
  - 背包里是否真的有该食物

- `GatherSkillPack.can_execute()`
  - 目标是否是合法食物源
  - 是否在空间记忆里可达

如果失败，执行层会记录：

- `skill_blocked`

然后清空当前动作，让下一轮重新规划。

这一步的意义是：

- LLM 可以犯错
- 但物理层不能让错误动作直接执行
- 技能包必须守住客观世界规则

---

## 3.10 第十步：Skill Pack.on_arrive() 完成真实结算

只有 `can_execute()` 通过，才会调用：

- `skill.on_arrive(persona, target, maze, personas)`

这一层才是真正的“技能执行”。

例如：

### Gather

- 往背包里增加食物
- 写入技能执行日志
- 饥饿时自动续接一个 `Consume` 动作

### Consume

- 扣除背包食物
- 增加 `satiety`
- 增加 `health`
- 可能提升 `mood`

### GenericActivitySkillPack

- 承接 `use/work/study/leisure_use`
- 做通用数值结算
- 清空当前动作

### ChatSkillPack

- 触发对话
- 写入记忆
- 更新关系图谱
- 还可能插入新的 follow-up action

这一步结束后，Skill Pack 一般会清理：

- `planned_path`
- `act_path_set`
- `act_address`
- `act_description`
- `act_event`
- `act_command`

表示当前技能已经完成。

---

## 4. 为什么要多加一层 act_command

这是当前架构里最重要的设计点之一。

过去系统更依赖：

- `detail -> event triple -> execute`

但本地模型在这条链上会出现明显漂移：

- 把 `gather` 说成 `search`
- 把动作翻成 `is`
- 或生成与注册技能不匹配的谓词

于是会导致：

- 执行层命不中技能
- `skill_missing`
- 到了目标却没有真正执行

为了解决这个问题，项目现在采用：

```text
LLM 自然语言
  -> 结构化 action/target/detail
  -> act_command.skill_id
  -> execute.py
```

这样做的收益是：

- 降低 `event triple` 漂移对执行的破坏
- 把执行依赖从“自然语言解释”切换成“结构化命令协议”
- 让日志更容易分析
- 让新技能扩展更稳定

---

## 5. 用一个完整例子串起来

下面用“饥饿时去冰箱拿苹果并吃掉”举例。

### 5.1 LLM 思考

```text
我很饿，库存里没有吃的，应该去冰箱找食物。
```

### 5.2 翻译成结构化动作

```json
{
  "action": "Gather",
  "target": "refrigerator",
  "detail": "opening the refrigerator to gather food items",
  "duration": 10,
  "reasoning": "Satiety is low and inventory is empty."
}
```

### 5.3 归一成内部 act_command

```json
{
  "skill_id": "gather",
  "target": "refrigerator",
  "source": "decision_translation",
  "raw_action": "Gather",
  "detail": "opening the refrigerator to gather food items"
}
```

### 5.4 解析地址

```text
the Ville:xxx:xxx:refrigerator
```

### 5.5 写入 Scratch

当前角色状态被更新为：

- `act_description = "opening the refrigerator to gather food items"`
- `act_address = "the Ville:...:refrigerator"`
- `act_command.skill_id = "gather"`

### 5.6 execute.py 到达后查表

```text
SKILL_REGISTRY["gather"] -> GatherSkillPack
```

### 5.7 GatherSkillPack 执行

- 检查冰箱是否是合法食物源
- 往背包里放入苹果
- 如果当前仍然饥饿，则自动继续安排 `consume apple`

### 5.8 下一轮 consume

新的 `act_command` 类似：

```json
{
  "skill_id": "consume",
  "target": "apple",
  "source": "post_gather_followup",
  "raw_action": "consume",
  "detail": null
}
```

之后执行层会命中 `ConsumeSkillPack`，真正完成吃苹果与恢复饱食度。

---

## 6. 当前链路中的关键数据结构

## 6.1 action translation 输出

```json
{
  "action": "Work",
  "target": "blackboard",
  "detail": "studying at the blackboard",
  "duration": 30,
  "reasoning": "This fits the current academic task."
}
```

特点：

- 更接近 LLM 语言层
- 人可读
- 但不够稳定，不适合直接执行

## 6.2 act_command

```json
{
  "skill_id": "study",
  "target": "blackboard",
  "source": "decision_translation",
  "raw_action": "Work",
  "detail": "studying at the blackboard"
}
```

特点：

- 面向执行层
- 是真正稳定的内部动作协议
- `skill_id` 才是最关键字段

## 6.3 skill registry

```python
{
    "study": GenericActivitySkillPack(...),
    "work": GenericActivitySkillPack(...),
    "use": GenericActivitySkillPack(...),
    "chat with": ChatSkillPack(),
}
```

特点：

- 是字符串到技能实现的最终映射
- 执行层只负责查表，不负责业务细节

---

## 7. 当前链路的调试入口

如果你要排查“自然语言为什么没有变成正确 skill”，建议按下面顺序看。

### 7.1 看 decision_snapshot

文件：

- `logs/translation_verify.jsonl`

看点：

- `intent`
- `decision.action`
- `decision.target`
- `decision.detail`

如果这里已经错了，问题在：

- thinking prompt
- action translation prompt
- schema 限制

### 7.2 看 target_resolution

看点：

- `act_command_skill`
- `new_address`
- `resolution_meta`

如果这里错了，问题在：

- `normalize_skill_id()`
- `action_target_resolver.py`
- arena/object fallback

### 7.3 看 action_execution_debug.jsonl

看点：

- `arrive`
- `skill_lookup`
- `skill_blocked`
- `skill_missing`

如果这里出现：

- `skill_missing`
  - 说明 `skill_id` 没命中注册表

- `skill_blocked`
  - 说明命中了技能，但物理前置条件不满足

### 7.4 看具体 skill_execution_debug.jsonl

看点：

- 某个 Skill Pack 是否真的进了 `on_arrive()`
- 数值和库存有没有真正变化

---

## 8. 当前架构的优点与边界

## 8.1 优点

- 保留了 LLM 的高层自主决策能力
- 不再把执行稳定性完全押在自然语言上
- skill 扩展更标准
- 日志链路更清晰
- 可以逐步把宽泛动作收紧成稳定 `skill_id`

## 8.2 边界

- `normalize_skill_id()` 仍然包含规则映射，属于“过渡期稳定器”
- `target` 地址解析仍然可能受空间记忆质量影响
- 如果 Prompt 输出太偏，前面仍可能产生错误动作，需要日志配合调试

换句话说，当前不是“纯 LLM 直接执行”，而是：

**LLM 决策 + 规则化结构化收敛 + 技能分发表执行**

这是一种更适合当前本地模型稳定性的工程折中方案。

---

## 9. 关键文件索引

- `reverie/backend_server/persona/cognitive_modules/plan.py`
  - 两阶段决策入口
  - 自然语言意图 -> 结构化动作 -> act_command

- `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`
  - LLM Prompt 调用
  - JSON 清洗与校验

- `reverie/backend_server/persona/prompt_template/v2/action_translation_v1.txt`
  - action translation 的结构化输出模板

- `reverie/backend_server/persona/prompt_template/v2/action_schema.json`
  - 动作类别与允许目标

- `reverie/backend_server/persona/cognitive_modules/action_command_utils.py`
  - `normalize_skill_id()`
  - `build_action_command()`
  - `infer_action_command_from_event()`

- `reverie/backend_server/persona/cognitive_modules/action_target_resolver.py`
  - 已知对象与已知 arena 的稳定解析

- `reverie/backend_server/persona/memory_structures/scratch.py`
  - `act_command` 的保存与更新

- `reverie/backend_server/persona/cognitive_modules/execute.py`
  - 到达后的 skill 分发器

- `reverie/backend_server/persona/cognitive_modules/skill_packs/__init__.py`
  - `SKILL_REGISTRY`

- `reverie/backend_server/persona/cognitive_modules/skill_packs/*`
  - 每个 skill 的真实物理结算实现

---

## 10. 最终结论

在当前项目里，“大模型返回的自然语言如何成为 skills”的真正答案是：

1. LLM 先生成自然语言意图
2. LLM 再把意图翻译成结构化动作 JSON
3. 代码用 `normalize_skill_id()` 把宽泛动作收敛成稳定 `skill_id`
4. 代码用 `build_action_command()` 生成内部协议 `act_command`
5. `plan.py` 解析目标地址并写入 `Scratch`
6. `execute.py` 读取 `act_command.skill_id`
7. `SKILL_REGISTRY` 把它映射到具体 `Skill Pack`
8. `can_execute()` 校验物理条件
9. `on_arrive()` 完成真正的技能执行与结算

所以，**自然语言不会直接变成 skill；它会先变成结构化动作协议，再由执行层映射成 skill。**

