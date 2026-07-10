# Generative Agents — 阶段1提示词画像与上下文生成系统设计

本文档定义阶段 1 决策提示词（`demand_thinking`）的生成方案。目标是将 [提示词1.txt](/Users/gun/mygame/generative_agents/提示词1.txt) 中的“示例 + 要求说明”落成可实现的系统设计，使 NPC 在每次做即时决策时，都能获得一份结构稳定、重点清晰、可持续更新的 Prompt 上下文。

本设计特别关注以下问题：
1. 如何向 LLM 注入沙盒世界的物理规则与系统内驱力（10 项）设计说明摘要。
2. 如何接入经验记忆，而不把记忆系统本身和 Prompt 系统耦死。
3. 如何组织社交关系信息，使其在社交相关决策中可用。
4. 如何将天生特质、后天特质、当前情景、生活方式、今日计划沉淀为 NPC 的可复用画像字段。
5. 如何定义这些字段的来源、存放位置、更新办法和更新频率。

---

## 1. 设计目标

阶段 1 提示词的职责不是直接输出可执行 JSON，而是让 LLM 先决定：

```text
“这个 NPC 在当前约束下，下一步最可行的即时动作想做什么？”
```

因此，阶段 1 上下文生成系统需要满足以下目标：

1. **重点优先明确**：Prompt 必须突出“主导动机 + 当前物理可行性 + 最新失败反馈”。
2. **长期画像稳定**：人格、身份、生活方式等长期信息不应每次从全量记忆临时总结。
3. **近期上下文新鲜**：经验记忆、失败反馈、附近资源、协作状态应在决策时动态编译。
4. **更新机制分层**：不同类型的信息应有不同的来源和更新频率，避免全部混进同一个大字段。
5. **可调试可追踪**：每个提示词字段都应能追溯到“来源系统”和“最近一次更新时间”。
6. **长期目标单独建模**：长期目标应单独成字段，作为行动与社交的核心长期驱动，而不是埋在一般背景摘要中。
7. **长期目标有生存兜底**：所有 NPC 的长期目标都应以“活下去”为底线，再在此基础上发展对世界的认识与个体化追求。

---

## 2. 总体架构

建议将阶段 1 提示词生成拆为两层：

1. **NPC 持久画像层（Persistent Prompt Profile）**
   存放稳定或半稳定的摘要字段，直接挂在 NPC 属性附近，供每次决策读取。
2. **决策临时编译层（Decision Prompt Compiler）**
   在每次触发 `demand_thinking` 之前，读取 NPC 画像、当前状态、动态规则、附近资源和记忆检索结果，组装成最终 Prompt。

在工程实现上，还应进一步区分两种计算方式：

1. **云模型预总结层（Cloud Pre-Summarization Layer）**
   低频调用云模型，对长期或日级字段进行总结，并将结果持久缓存。
2. **本地即时编译层（Local Runtime Compilation Layer）**
   在每次决策触发时，用本地规则和当前状态快速生成即时字段。

总体流程如下：

```text
NPC 结构化状态 / motive 数值 / 技能 / 关系 / 记忆流
  -> Cloud Pre-Summarizers（低频或定时更新）
  -> NPC 持久画像字段

当前 step 状态 / 上一步执行结果 / 附近资源 / InvalidTargets / 记忆检索
  -> Local Runtime Compiler（每次决策实时执行）
  -> Stage 1 Prompt
  -> LLM 输出一句自然语言 thought
```

---

## 3. 阶段1提示词的目标结构

以 [提示词1.txt](/Users/gun/mygame/generative_agents/提示词1.txt) 为阅读示例，程序侧的阶段 1 Prompt 结构建议保持以下语义层次：

1. `Decision Capsule`
   当前时间、当前状态、主次动机、当前规则、当前附近可达资源、协作状态、经验记忆、社交关系、收敛提示。
2. `Background Identity`
   天生特质、后天特质、长期目标、当前情景、生活方式、今日计划。
3. `Priority Rules`
   主导动机优先、可行性优先、失败反馈优先、长期目标是核心长期驱动但不能压过即时生存与物理约束。
4. `Task`
   只要求一句第一人称 thought，只提一个即时动作和一个目标。

其中：
- `Decision Capsule` 以动态信息为主。
- `Background Identity` 以持久画像字段为主。
- `Priority Rules` 以程序模板或常量为主。

---

## 4. 数据分类原则

本设计将阶段 1 所需信息分为四类：

### 4.1 固定规则类
由程序生成或维护，不交给 LLM 自行总结。

示例：
- inventory 为空时不能直接 `Consume`
- `Satiety` 归零会持续损失 `Health`
- `InvalidTargets` 本 step 禁选

特点：
- 高可靠
- 实时性强
- 不依赖记忆系统

### 4.2 稳定画像类
适合挂在 NPC 属性中，直接读取。

示例：
- 天生特质
- 后天特质
- 当前情景
- 生活方式
- 今日计划

特点：
- 中长期复用
- 更新频率可控
- 不应每次决策重新总结

### 4.3 动态检索类
每次决策时重新计算。

示例：
- 经验记忆
- 当前社交关系摘要
- 当前主次动机说明
- 当前失败反馈
- 当前附近可达资源

特点：
- 强依赖当前上下文
- 不适合长期缓存成固定字段

### 4.4 结构化原始状态类
作为编译输入，不直接暴露给 LLM 或只转成自然语言后暴露。

示例：
- motive 数值
- 当前 inventory
- 最近动作结果
- 最近失败对象
- 长短期记忆原始节点
- 关系图结构化数值

---

## 5. 云模型预总结与本地即时编译分层

本系统并不适合把所有字段都放在“每次决策时现算”。按照当前设计，很多字段需要事先请求云模型完成总结，然后把结果持久保存下来，供运行时直接读取。

否则会带来三个问题：
- 每次决策都重复做高成本总结，云调用成本过高
- 长期画像在每个 step 上漂移，角色稳定性下降
- 单步决策延迟过高，难以支撑高频运行

因此，字段应分为三类：

### 5.1 必须预先请求云模型总结的字段

这些字段适合低频、异步、缓存化生成：

- `learned_traits_text`
- `current_situation_text`
- `long_term_goals_text`
- `lifestyle_text`
- `daily_plan_text`
- `social_relationships_text`

原因：
- 它们本质上都需要对较大范围的记忆、行为、关系或身份材料进行抽象压缩
- 纯规则很难生成质量稳定、可读性高的文字
- 若在每步决策时现算，会既贵又慢

### 5.2 可选云总结、但必须先走本地检索/筛选的字段

- `relevant_experience_text`

推荐流程：
1. 本地检索候选记忆
2. 本地做相关性排序和裁剪
3. 必要时调用云模型把 top-k 记忆压成短摘要

原因：
- 检索阶段应本地完成
- 但最后一层“压成几句高可读经验”通常云模型更稳

### 5.3 必须本地即时生成的字段

- `world_rules_text`
- `drive_system_summary_text`
- `motive_guidance_text`
- nearby 资源摘要
- 最新失败反馈
- `InvalidTargets`
- `decision_social_context_text` 中与“当前 nearby / 当前 obligation / 当前冲突”相关的即时部分

原因：
- 这些字段直接依赖当前 step 的客观状态
- 它们需要高实时性、强可控性和低延迟
- 不适合交给云模型做临场总结

### 5.4 推荐的运行分层

#### 长周期云总结

负责：
- `learned_traits_text`
- `current_situation_text`
- `long_term_goals_text`
- `lifestyle_text`

触发：
- 重大事件
- 长期目标变化
- 技能/身份变化
- 定期刷新

#### 日级云总结

负责：
- `daily_plan_text`

触发：
- day start
- replan

#### 决策前轻量云总结

负责：
- `relevant_experience_text`（仅在本地检索结果足够复杂时）

触发：
- 决策触发
- 仅在需要压缩候选经验时调用

#### 本地即时编译

负责：
- 规则
- 当前主次动机
- 资源可达性
- 失败反馈
- nearby 社交上下文

触发：
- 每次 `demand_thinking`

### 5.5 设计要求

- 不要让 `demand_thinking` 在每一步都重新总结长期画像
- 不要把长期画像生成和即时规则编译混成一个函数
- 所有云总结字段都应持久缓存，并记录最近更新时间
- 所有本地即时字段都应保证在无云情况下也能生成

---

## 6. NPC 持久画像字段设计

建议在 NPC 的属性系统中增加一个与 motive、identity、stable memory 相邻的画像区域。它可以是 `scratch` 邻近结构，也可以是单独的 profile 对象，但应与角色核心属性一起持久化。

建议字段如下：

### 6.1 天生特质 `innate_traits_text`

含义：
- 用自然语言概括角色较稳定的基础性格倾向。

来源：
- 角色初始化设定
- 初始 motive 值分布
- archetype / seed persona 描述

更新方式：
- 初始化时生成
- 默认不自动更新
- 仅在角色重建或人工重置时更新

设计理由：
- 天生特质应是稳定的“人格底色”，不应被短期行为频繁改写。

### 6.2 后天特质 `learned_traits_text`

含义：
- 总结技能特长、长期职责、重复成功经验沉淀出的能力倾向。

来源：
- 技能系统中的显式技能
- 长期高频成功行为
- 角色职责与职业身份
- 长期经验记忆中的重复模式

更新方式：
- 低频更新
- 在技能显著提升、职责变化、某类行为积累到阈值时更新

设计理由：
- 后天特质不是临时动作能力列表，而是“这个人擅长什么”的稳定摘要。

### 6.3 当前情景 `current_situation_text`

含义：
- 用于概括角色当前所处阶段、近期重要背景、正在推进的阶段性事情。

来源：
- 可使用全部记忆数据
- 通过专门的 LLM 总结函数生成

内容要求：
- 应体现当前阶段性任务背景
- 应避免只写最近一步动作

更新方式：
- 低频更新
- 重大事件发生时触发
- 或每隔若干模拟天定期刷新

设计理由：
- 当前情景是“角色这段时间正在经历什么”的阶段性背景，不应每步都重新写。

### 6.4 长期目标 `long_term_goals_text`

含义：
- 用于明确描述角色长期想达成什么、长期在追求什么，以及这些目标为何重要。
- 该字段必须包含一个统一的兜底长期目标：`活下去`。
- 在“活下去”之上，再描述 NPC 基于记忆形成的世界认识，以及在该认识基础上如何尽可能满足自己的内驱力与天生特质。

来源：
- 长期记忆数据
- 反思产物
- 角色身份设定
- 专门的 LLM 总结函数

内容要求：
- 应包含统一兜底项：`活下去`
- 应明确写出长期目标或长期计划
- 应体现 NPC 如何理解自己所处的沙盒世界
- 应体现 NPC 认为“在这个世界里，要怎样做才能在活下去的前提下尽可能满足自己的内驱力与人格倾向”
- 应体现角色在行动和社交上的深层方向
- 应避免退化成“今天要做什么”的短期安排

建议表达形态：
- 第一层：生存兜底
- 第二层：世界认识
- 第三层：在该世界认识基础上的长期追求

示例：
- `首先要活下去。在这个资源有限、食物来源单一的封闭世界里，我需要持续找到可行的食物与休息方式，避免让自己陷入无法恢复的状态。在活下去的基础上，我会尽量按照自己友善、外向、好客的天性去经营与他人的关系，并通过照顾他人、维持体面秩序和完成自己的职责来满足内驱力。`

更新方式：
- 低频更新
- 长期目标变化时触发
- 重大人生事件或长期任务转折时触发
- 或按较长周期定期刷新

设计理由：
- 长期目标是人物行动和社交的真正核心长期驱动之一
- 它应单独成字段，避免被混在 `current_situation_text` 中被稀释
- 明确加入“活下去”这一兜底项后，长期目标就既有稳定底线，又能承载角色个体化的世界理解与追求方向

### 6.5 生活方式 `lifestyle_text`

含义：
- 用于概括作息、日常偏好、常见习惯、稳定的生活节奏。

来源：
- 长期记忆数据
- 长期行为统计
- 专门的 LLM 总结函数

更新方式：
- 中频更新
- 作息和稳定行为模式明显变化时触发
- 或按固定周期重算

设计理由：
- 生活方式属于稳定但可缓慢变化的信息，例如起床时间、晚睡习惯、常去地点。

### 6.6 今日计划 `daily_plan_text`

含义：
- 用于描述当天的主要安排和日内职责。

来源：
- 短期记忆数据
- 当日 agenda
- 当天早晨或 day start 触发的 LLM 总结

更新方式：
- 每天计划一次
- 若日内遭遇重大打断，可触发一次 replan 或附加更新

设计理由：
- 今日计划天然是日级别字段，不应和长期画像混在一起。

### 6.7 社交关系摘要 `social_relationships_text`

含义：
- 总结该 NPC 当前具有代表性的社会关系结构和关键关系倾向。
- 当涉及重要他人时，附带这些他人的天生特质说明，作为静态关系背景的一部分。

来源：
- 关系系统的结构化数值
- 近期互动记忆
- 其他 NPC 的 `innate_traits_text`
- 可由程序先选出“重要关系”，再交由 LLM 总结

应包含的信息：
- 我与哪些 NPC 关系最重要
- 这些关系当前处于什么状态
- 对当前角色而言，这些对象扮演什么社会角色
- 这些对象的天生特质静态说明

关于“其他 NPC 的天生特质说明”的要求：
- 来源于对方 NPC 的 `innate_traits_text`
- 纯静态
- 不跟随对方当前情绪、当前动作或短期状态变化
- 用于帮助 LLM 理解“这个人平时是什么样的人”，而不是“他现在这一刻表现如何”

更新方式：
- 中频更新
- 关系显著变化时触发
- 或在社交相关关键事件后刷新

设计理由：
- 社交关系比天生特质更动态，但也不必每次决策都从全量关系图重新生成。
- 把“他人的静态天生特质”作为关系背景的一部分，能够在社交判断中提供稳定的人物理解。

---

## 7. 动态上下文字段设计

以下字段不建议长期固定存储，而应在阶段 1 决策前临时生成。

### 7.1 规则说明 `world_rules_text`

作用：
- 告诉 LLM 这个沙盒世界当前对本步决策最重要的客观约束。

内容来源：
- 世界物理规则
- 当前状态触发的生理规则
- 当前资源可用性
- 当前 inventory
- 最新失败反馈
- `InvalidTargets`

生成方式：
- 完全由程序侧生成
- 不依赖 LLM 总结

必须覆盖的信息：

1. **沙盒世界的物理规则**
   例如：
   - inventory 为空时不能直接 `Consume`
   - 目标如果在 `InvalidTargets` 中，本 step 禁止再选
   - 某资源已空或不可达

这里需要注意：
- 世界规则本身不应由 LLM“总结后再告诉自己”
- 不应把“当前主导动机/次级动机”混进规则说明本体

### 7.2 内驱力系统设计摘要 `drive_system_summary_text`

作用：
- 向 LLM 说明本系统采用哪 10 项内驱力，以及这些内驱力在决策中大致代表什么。

性质：
- 纯静态文本
- 与当前 NPC 的实时状态无关
- 与当前 step 的主次动机无关

内容来源：
- 系统设计常量
- 动机系统文档约定

示例内容：
- `satiety`: 饱腹需求，低时更倾向寻找和获取食物
- `stamina`: 精力需求，低时更倾向休息或睡眠
- `health`: 身体完整性与恢复需求
- `safety`: 安全与避险需求
- `mood`: 情绪修复需求
- `belonging`: 社交归属需求
- `status`: 地位与认可需求
- `autonomy`: 自主与自我决定需求
- `competence`: 胜任与掌控需求
- `meaning`: 目标感与意义需求

生成方式：
- 写成固定模板或静态配置
- 不在每次决策时重新总结

设计理由：
- 这部分描述的是“系统如何理解 10 项内驱力”
- 不是“这个人物当前此刻正在被哪项内驱力主导”

### 7.3 经验记忆 `relevant_experience_text`

作用：
- 给 LLM 注入“这次决策最相关的经验”，而不是全部记忆。

来源：
- 独立记忆系统检索结果

设计原则：
- 经验记忆应来自记忆筛选，不属于持久画像字段
- Prompt 系统只消费其摘要结果，不重做记忆系统本身

建议流程：
1. 根据当前上下文构造检索 query
2. 检索记忆候选
3. 按相关性排序
4. 选取 top-k
5. 压缩成 2 到 5 句自然语言摘要

优先命中的经验类型：
- 最近失败的相同目标
- 在相同 motive 下成功的方案
- 在相同地点成功或失败的方案
- 与当前 nearby 人物相关的社交经验

更新方式：
- 每次决策动态生成
- 可短缓存，但不写回稳定画像

### 7.4 社交关系 `decision_social_context_text`

作用：
- 在当前 step 中，只给出和本次决策相关的社交关系上下文。

来源：
- `social_relationships_text`
- 当前 nearby 角色
- 当前社交 obligations
- 最新互动状态
- nearby 相关角色的 `innate_traits_text`

设计原则：
- 不是把完整关系图塞进 Prompt
- 而是只提“与这一步相关的人”
- 当提到某个相关 NPC 时，应尽量附带其静态天生特质说明

例如：
- 附近有一位高亲密对象，适合在 `mood` 主导时作为社交目标
- 当前有人在等我提供服务
- 我和某人最近刚发生冲突，不适合作为优先社交对象
- Klaus Mueller：天生特质 `kind, inquisitive, passionate`，与我关系亲近，适合作为稳定的社交对象
- Isabella Rodriguez：天生特质 `friendly, outgoing, hospitable`，当前正在承担服务义务

更新方式：
- 每次决策动态编译

注意：
- 这里引用的“其他 NPC 天生特质”是静态字段
- 它不应被 recent chat、当前 mood 或当前动作即时改写

### 7.5 主次动机说明 `motive_guidance_text`

作用：
- 把 motive 数值转成 LLM 易理解的中文或英文主观句。

来源：
- motive selector
- state dynamics

示例：
- `我很饿，我很想进食。`
- `我情绪很差，我想提升一下情绪。`

更新方式：
- 每次决策实时生成

---

## 8. 规则说明的设计要求

“规则说明”是本系统最关键的部分之一，必须明确告诉 LLM：

1. **这个世界客观上允许什么，不允许什么**
2. **这个系统中的 10 项内驱力分别代表什么**

建议将与阶段 1 有关的“规则与驱动说明”拆成三层：

### 8.1 全局稳定规则

由代码维护，适用于所有 NPC。

示例：
- 背包无食物时不能 `Consume`
- `Satiety` 或 `Stamina` 归零会带来生理损伤
- 物理不可达目标不应继续重试

### 8.2 当前世界状态规则

由当前地图、库存、路径、失败反馈生成。

示例：
- 已知城镇食物来源当前已枯竭，仅 `apple tree` 可用
- `behind the cafe counter` 库存为空
- `apple tree` 刚刚执行失败，当前 step 禁止继续选它

### 8.3 内驱力系统静态说明

由系统设计常量维护，是纯静态说明。

示例：
- `satiety` 代表饱腹需求
- `mood` 代表情绪修复需求
- `competence` 代表胜任和掌控需求
- 多项内驱力共同参与排序，系统会在每个 step 选择主导动机和次级动机

重要约束：
- 规则说明必须由程序侧稳定生成
- 不要让 LLM 自己先“理解世界规则”，再把世界规则口语化后回灌给自己
- 不要把“当前谁是主导动机”写进这段静态说明里

### 8.4 当前主次动机说明

由 motive selector 和当前状态编译得到，是动态文本。

示例：
- 当前主导动机是 `satiety`
- 当前次级动机是 `mood`
- 如果 `Satiety` 极低，当前这一步应显著提高找食物的优先级

重要约束：
- 这部分属于 `motive_guidance_text`
- 它描述的是“当前这位 NPC 此刻的内在压力排序”
- 不应和 10 项内驱力的系统静态说明混写

---

## 9. 各字段的更新频率与触发机制

| 字段 | 来源 | 更新频率 | 更新触发 |
| :--- | :--- | :--- | :--- |
| `innate_traits_text` | 初始角色设定 + 初始 motive | 极低 | 初始化 / 人工重建 |
| `learned_traits_text` | 技能与长期成功经验 | 低 | 技能变化 / 职责变化 / 行为模式稳定变化 |
| `current_situation_text` | 全量记忆总结 | 低 | 重大事件 / 阶段变化 / 定期刷新 |
| `long_term_goals_text` | 长期记忆 + 反思 + 身份设定 | 低 | 长期目标变化 / 重大转折 / 定期刷新 |
| `lifestyle_text` | 长期记忆与行为统计 | 中 | 作息或生活节律变化 / 定期刷新 |
| `daily_plan_text` | 短期记忆与当日 agenda | 每天一次 | day start / replan |
| `social_relationships_text` | 关系结构 + 近期互动 | 中 | 关系变化 / 社交关键事件 |
| `world_rules_text` | 程序规则编译 | 每次决策 | 决策触发 |
| `drive_system_summary_text` | 系统静态模板 | 极低 | 常量初始化 / 手工更新 |
| `motive_guidance_text` | motive 数值编译 | 每次决策 | 决策触发 |
| `relevant_experience_text` | 记忆检索 | 每次决策 | 决策触发 |
| `decision_social_context_text` | 关系 + nearby 角色 + 他人静态天生特质 | 每次决策 | 决策触发 |

---

## 10. 阶段1 Prompt 的编译流程

建议在触发 `demand_thinking` 之前，按以下顺序组装 Prompt：

### 10.1 读取稳定画像字段

从 NPC 属性中读取：
- `innate_traits_text`
- `learned_traits_text`
- `current_situation_text`
- `long_term_goals_text`
- `lifestyle_text`
- `daily_plan_text`
- `social_relationships_text`

### 10.2 编译决策胶囊

实时收集：
- 当前时间
- 当前 stats
- 当前 inventory
- 当前主次动机
- 上一个动作和执行反馈
- 当前附近关键可达资源
- 当前协作状态
- `InvalidTargets`

### 10.3 生成动态文本

调用：
- `build_world_rules_text()`
- `build_drive_system_summary_text()`
- `build_motive_guidance_text()`
- `retrieve_relevant_experience_text()`
- `build_decision_social_context_text()`

### 10.4 拼装成阶段1 Prompt

输出结构建议：

```text
Decision Capsule:
  Time
  Decision Priority
  Last Action
  Rules
  Drive System Summary
  Motives
  Nearby Reachable Resources
  Cooperative Context
  Experience Memory
  Social Relationship Context

Background Identity:
  Name
  Age
  Innate Traits
  Learned Traits
  Long-Term Goals
  Current Situation
  Lifestyle
  Daily Plan

Priority Rules:
  ...

Task:
  ...
```

### 10.5 调用阶段1模型

最终输出要求仍然是：
- 第一人称
- 只一句
- 只说一个即时动作
- 只提一个目标物体或地点
- 明确当前最迫切的内部需求

---

## 11. 与记忆系统、动机系统和关系系统的边界

为了避免系统之间职责混乱，本设计明确以下边界：

### 11.1 与记忆系统的边界

- 记忆系统负责存储、检索、排序和召回
- Prompt 系统只消费“已经筛选出的经验摘要”
- `relevant_experience_text` 不负责改写记忆库

### 11.2 与动机系统的边界

- 动机系统负责计算主导动机、次级动机、压力值
- Prompt 系统负责把这些结果翻译成 LLM 易理解的文字
- Prompt 系统不重新定义 motive 选择逻辑

### 11.3 与关系系统的边界

- 关系系统负责结构化维护 affinity / trust / social obligations 等
- Prompt 系统负责把“当前决策相关的关系部分”压缩到可读文本

### 11.4 与计划系统的边界

- `daily_plan_text` 是日级计划摘要
- 阶段 1 Prompt 只把它当作低优先级背景
- 当前物理可行性、失败反馈和主导动机优先级更高

---

## 12. 反思阶段产物的复用策略

原系统的记忆设计中已经存在 `reflect` 阶段。该阶段会基于近期事件和 thought 进行聚合、检索和再总结，产出更高层级的 insight / thought。这些产物不应被忽略，它们是构建阶段 1 Prompt 画像字段的重要上游材料。

### 12.1 原系统中反思阶段的已有产物

根据当前实现，反思阶段主要产出以下几类信息：

1. **高层 insight / thought**
   - 来自 `generate_insights_and_evidence()`
   - 本质是对近期记忆的抽象总结，并附带 evidence 节点
   - 会作为新的 `thought` 写回记忆库

2. **对话后的 planning thought**
   - 对一次聊天或社交事件结束后，提炼“这次对话对接下来计划有什么影响”
   - 会作为新的 `thought` 写回记忆库

3. **对话后的 memo thought**
   - 对一次聊天或社交事件结束后，提炼“我如何看待这次对话或这段关系”
   - 会作为新的 `thought` 写回记忆库

这些反思产物具有两个优点：
- 比原始事件更抽象、更接近人类主观理解
- 已经过一次筛选与压缩，更适合做长期画像更新的原材料

### 12.2 哪些字段适合利用反思产物

最适合利用反思产物的字段如下：

#### `current_situation_text`

适合来源：
- 高层 insight / thought
- planning thought
- 高 poignancy 的长期事件记忆

原因：
- 当前情景需要描述“这个角色最近处于什么阶段、正在推进什么事情”
- 这些内容正好是反思机制擅长抽象的对象

#### `long_term_goals_text`

适合来源：
- 高层 insight / thought
- planning thought
- 长期重复出现的 mission-like 反思结果
- 与身份和人生方向反复相关的高 poignancy 记忆

原因：
- 长期目标需要概括“这个角色真正长期在追求什么”
- 长期目标还需要概括“这个角色如何理解自己所处的世界，以及如何在这个世界里先活下去，再追求其他东西”
- 反思产物比原始事件更适合提炼这种深层方向

#### `learned_traits_text`

适合来源：
- 长期重复出现的 insight / thought
- 与技能、职责、成功经验反复关联的反思结果

原因：
- 后天特质本质上是“反复做成某些事后沉淀下来的能力与倾向”
- 直接从单次事件抽取容易不稳，从多次反思产物归纳更稳

#### `social_relationships_text`

适合来源：
- memo thought
- 对话相关的 planning thought
- 与特定他人反复相关的 insight
- 其他 NPC 的静态 `innate_traits_text`

原因：
- 反思产物更容易显式表达“我如何看待某人”“这次互动改变了什么”
- 比原始聊天文本更适合做关系层摘要
- 但他人的天生特质说明应继续来自对方的静态字段，而不是由反思结果改写

#### `relevant_experience_text`

适合来源：
- 高 poignancy 的 thought 节点
- 带有 evidence 的 insight 节点
- 最近的 planning thought

原因：
- 阶段 1 检索经验记忆时，不应只搜原始 event
- 已经反思过的 thought 往往是更高价值的经验浓缩样本

### 12.3 哪些字段不适合直接使用反思产物

以下字段不建议直接由反思产物生成：

#### `innate_traits_text`

原因：
- 天生特质应保持稳定
- 反思产物是动态经验总结，不适合作为人格底色的直接来源

#### `world_rules_text`

原因：
- 规则说明必须由程序稳定控制
- 不能依赖 LLM 的主观反思去定义世界规则

#### `drive_system_summary_text`

原因：
- 这是一份系统级静态设计摘要
- 不应由反思产物驱动
- 不应混入任何当前 NPC 的即时状态

#### `motive_guidance_text`

原因：
- 当前内驱力应来自 motive 数值和状态编译
- 反思可作为补充背景，但不应替代当前状态计算

#### `daily_plan_text`

原因：
- 虽然 planning thought 可提供参考
- 但今日计划的主来源仍应是短期记忆和当天 agenda，而不是反思结果本身

### 12.4 推荐的复用方式

推荐方式不是“把反思结果原样塞进阶段 1 Prompt”，而是：

```text
Reflect 产物
  -> 写回记忆库（thought / insight / planning_thought / memo_thought）
  -> 作为高权重候选材料参与画像更新
  -> 画像字段更新器输出 current_situation / long_term_goals / learned_traits / social_relationships
  -> 阶段1 Prompt 读取这些画像字段
```

也就是说，反思产物应当作为：
- 持久画像更新器的输入
- 经验记忆检索器的高价值候选

而不是直接作为最终 Prompt 文本块。

### 12.5 推荐的数据流

建议增加一层“反思产物消费器（reflection product consumer）”，其流程如下：

1. `reflect` 继续按现有机制写入高层 `thought`
2. 画像更新器在低频更新时，优先读取：
   - 最近一段时间的高 poignancy `thought`
   - 最近的 planning thought
   - 最近的 memo thought
3. 对这些 thought 做主题聚类或简单筛选
4. 分别喂给不同的 summarizer：
   - `summarize_current_situation_from_reflections()`
   - `summarize_learned_traits_from_reflections()`
   - `summarize_relationships_from_reflections()`
5. 更新对应画像字段

### 12.6 对阶段1 Prompt 的直接价值

反思产物对阶段 1 Prompt 的价值主要体现在两个层面：

1. **提升长期画像质量**
   - 当前情景不再只依赖硬编码身份文本
   - 后天特质能反映角色真实成长
   - 社交关系摘要更贴近近期互动演化

2. **提升经验记忆质量**
   - 被反思过的 thought 比原始事件更像“可迁移经验”
   - 更适合在阶段 1 中作为“Relevant Prior Experience”输入

3. **支撑长期目标字段**
   - 反思产物更容易沉淀出稳定的长期追求
   - 适合作为 `long_term_goals_text` 的重要上游材料

### 12.7 注意事项

#### 不要把反思 thought 原样直接塞进阶段1 Prompt

原因：
- 反思文本常常比较抽象
- 可能和当前这一步的即时决策不直接相关
- 容易增加叙事噪声

#### 不要让反思结果覆盖当前物理现实

原因：
- 反思是长期抽象
- 当前 step 的物理可行性、失败反馈和附近资源优先级更高

#### 不要让单次反思直接改写稳定人格

原因：
- 单次事件可能过度放大短期波动
- 稳定人格字段应依赖长期统计或长期多次反思聚合

---

## 13. 推荐实现顺序

为降低改造风险，建议按以下顺序分阶段实现：

### 13.1 第一阶段：落地持久画像字段

优先实现：
- `innate_traits_text`
- `learned_traits_text`
- `current_situation_text`
- `long_term_goals_text`
- `lifestyle_text`
- `daily_plan_text`

目标：
- 让阶段 1 Prompt 能先从 NPC 属性中直接读取稳定背景

### 13.2 第二阶段：接入动态编译字段

实现：
- `build_world_rules_text()`
- `build_drive_system_summary_text()`
- `build_motive_guidance_text()`
- `build_decision_social_context_text()`
- `retrieve_relevant_experience_text()`

目标：
- 让 Prompt 真正体现当前 step 的实时状态

### 13.3 第三阶段：接入反思产物复用

实现：
- `summarize_current_situation_from_reflections()`
- `summarize_long_term_goals_from_reflections()`
- `summarize_learned_traits_from_reflections()`
- `summarize_relationships_from_reflections()`

目标：
- 让已有 reflect 系统真正参与 Prompt 画像构建

### 13.4 第四阶段：接入调试与日志

建议记录：
- 每个字段的来源
- 最近更新时间
- 最终进入 Prompt 的值
- 触发本次更新的原因

目标：
- 支持分析“哪个字段淹没了重点”
- 支持回放和 Prompt 调优

---

## 14. 风险与注意事项

### 14.1 不要把所有字段都做成每次实时 LLM 总结

否则会带来：
- token 成本暴涨
- 信息漂移
- 稳定人格丢失

### 14.2 不要把长期画像和短期经验混成一个字段

否则会导致：
- 角色背景被最新事件污染
- Prompt 重点混乱

### 14.3 不要让“技能特长”覆盖“即时可行性”

后天特质只能告诉 LLM“这个角色擅长什么”，不能替代“这一步现在能做什么”。

### 14.4 不要让长期目标压过当前生理和物理约束

`long_term_goals_text` 是人物行动和社交的核心长期驱动之一，但在单步决策中，仍不能凌驾于当前求生、执行可行性和最新失败反馈之上。`current_situation_text` 和 `daily_plan_text` 也不能凌驾于这些即时约束之上。

补充说明：
- `long_term_goals_text` 自身内部应始终包含“活下去”这一兜底目标
- 这意味着长期目标并不与生存对立，而是在生存底线之上组织更个体化的长期追求

---

## 15. 结论

阶段 1 Prompt 的质量，不取决于“塞给 LLM 的信息越多越好”，而取决于是否建立了：

1. 稳定的 NPC 持久画像字段
2. 清晰的当前规则说明
3. 动态但受控的经验记忆检索
4. 单独建模并维护长期目标字段
5. 对 reflect 产物的分层复用
6. 与记忆、动机、社交系统职责清晰分离的编译流程

其中，长期目标字段不应只是普通的“人生愿望描述”，而应同时承载：
- 生存兜底目标
- 对沙盒世界的长期认识
- 在该认识之上尽可能满足内驱力与天生特质的个体化方向

按照本设计落地后，[提示词1.txt](/Users/gun/mygame/generative_agents/提示词1.txt) 中的“示例 + 要求说明”就可以从人工整理稿，演进为程序内可持续生成、可更新、可调试的阶段 1 提示词系统。
