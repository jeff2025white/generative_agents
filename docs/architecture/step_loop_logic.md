# Generative Agents — 当前 Step 循环运算链路说明

> 本文档基于当前仓库源码，重新梳理一次真实的 `step` 运算链路，作为后续决策系统改造的前期调研基础。
>
> 本文档以源码为准，重点覆盖：
> - 后端 step 主循环
> - 单个 persona 的 `move()` 认知链
> - `plan()` / `decide_demand_action()` / `execute()` 的真实职责边界
> - 前端、Django、movement/environment 与存档落盘的交互关系
>
> 核心入口：
> - [start_server](file:///g:/generative_agents/reverie/backend_server/reverie.py#L362-L820)
> - [move](file:///g:/generative_agents/reverie/backend_server/persona/persona.py#L210-L342)

---

## 1. 文档目标

这份文档不再描述旧版“长日程 + 多级位置生成 + 自动保存每 10 步”的历史实现，而是回答下面四个问题：

1. 当前一个 `step` 从哪里开始，按什么顺序运行
2. 当前 persona 的认知与执行链路到底是怎样串起来的
3. 当前“意图生成”和“动作翻译”在哪一层被压缩到一起
4. 后续如果要做 action layer / world model 改造，最值得插手的点在哪里

---

## 2. 当前整体架构

当前 step 运算的整体结构可以概括为：

```text
ReverieServer.start_server()
  -> 环境同步 / 待处理动作注入 / 世界状态回写 / 代谢更新
  -> 并发 persona.move()
       -> 快路径执行
       -> 或完整链: perceive -> retrieve -> plan -> reflect -> execute
  -> 汇总 movement
  -> movement 落盘 + 发 Django
  -> step + 1, curr_time 推进, 增量保存
```

从职责上看，当前系统更像：

- `ReverieServer`：step 级世界调度器
- `Persona.move()`：单角色 step 编排器
- `scratch`：单角色运行期控制中枢
- `decide_demand_action()`：压缩式联合决策层
- `execute()`：路径生成 + 到达分发 + 执行守卫

---

## 3. Step 主循环总览

主循环入口是 [start_server](file:///g:/generative_agents/reverie/backend_server/reverie.py#L362-L820)。

单个 step 的真实执行顺序如下：

1. 获取当前 step 的环境状态
2. 拉取并注入待处理的 creator / user 动作
3. 清理上一步残留的对象事件
4. 把前端环境位置同步回后端 maze
5. 更新所有 persona 的代谢与情绪状态
6. 并发执行所有 persona 的 `move()`
7. 汇总 movement 数据
8. movement 同时写本地文件并异步发 Django
9. 推进 `step` 与 `curr_time`
10. 做增量记忆保存

对应核心代码段：

- 环境同步：[reverie.py](file:///g:/generative_agents/reverie/backend_server/reverie.py#L400-L479)
- 待处理动作注入：[reverie.py](file:///g:/generative_agents/reverie/backend_server/reverie.py#L481-L535)
- 世界状态回写：[reverie.py](file:///g:/generative_agents/reverie/backend_server/reverie.py#L537-L576)
- 代谢更新：[reverie.py](file:///g:/generative_agents/reverie/backend_server/reverie.py#L577-L636)
- 并发 persona.move：[reverie.py](file:///g:/generative_agents/reverie/backend_server/reverie.py#L645-L744)
- movement 持久化：[reverie.py](file:///g:/generative_agents/reverie/backend_server/reverie.py#L757-L776)
- step/time 推进与增量保存：[reverie.py](file:///g:/generative_agents/reverie/backend_server/reverie.py#L778-L819)

---

## 4. 环境同步与前后端锁步

### 4.1 环境读取优先级

当前 step 开始时，后端按以下优先级拿环境：

1. Django API：`/api/get_environment/`
2. 本地文件：`storage/<sim_code>/environment/<step>.json`
3. 后端自持的 `personas_tile`

对应代码：[reverie.py](file:///g:/generative_agents/reverie/backend_server/reverie.py#L400-L479)

### 4.2 前端活跃时的等待机制

后端会检查 `temp_storage/frontend_active_<sim_code>.json` 心跳文件。如果前端活跃且当前 step 环境还没到，后端会轮询等待前端推进，而不是立即独立续跑。

对应代码：

- 后端等待逻辑：[reverie.py](file:///g:/generative_agents/reverie/backend_server/reverie.py#L410-L449)
- 前端心跳写入：[views.py](file:///g:/generative_agents/environment/frontend_server/translator/views.py#L30-L36)

### 4.3 前端 step 的三阶段循环

浏览器端的 step 不是直接跑认知，而是走：

- `process`
- `update`
- `execute`

其中：

- `process` 把当前环境 POST 回 Django
- `update` 轮询 movement
- `execute` 播放 movement 并让前端 step 自增

对应代码：[main_script.html](file:///g:/generative_agents/environment/frontend_server/templates/home/main_script.html#L420-L589)

---

## 5. 世界状态同步与代谢更新

在进入 persona 认知之前，后端先做两类底层状态更新。

### 5.1 世界状态同步

后端会先把上一轮记录在 `game_obj_cleanup` 中的对象事件恢复为空，再把当前 persona 的位置和对象事件写回 maze。

对应代码：[reverie.py](file:///g:/generative_agents/reverie/backend_server/reverie.py#L537-L576)

### 5.2 生理与情绪状态更新

当前版本每个 step 都会先统一更新：

- `satiety`
- `stamina`
- `mood`
- `health`

这是在 persona 做认知决策之前完成的，因此 persona 在本 step 看到的是已经衰减后的状态。

对应代码：[reverie.py](file:///g:/generative_agents/reverie/backend_server/reverie.py#L577-L636)

当前生理衰减的真实特点：

- 数值已经是小步长连续衰减，不是旧文档里的大幅扣减
- `sleep/rest/walk/normal activity` 的衰减和恢复速率不同
- `mood` 与 `satiety/stamina/chatting_with` 联动
- `health` 在饥饿、精力枯竭、情绪极低时扣减，并在多项状态良好时缓慢恢复

---

## 6. Persona.move()：单角色 Step 编排器

单角色 step 入口是 [move](file:///g:/generative_agents/reverie/backend_server/persona/persona.py#L210-L342)。

它的职责不是“做某一个认知模块”，而是决定本角色这一 step 走哪条流水线。

### 6.1 进入时先写入运行态

一开始就会写入：

- `scratch.curr_tile`
- `scratch.curr_step`
- `scratch.curr_time`

对应代码：[persona.py](file:///g:/generative_agents/reverie/backend_server/persona/persona.py#L230-L257)

### 6.2 死亡短路

如果 `health <= 0`，角色直接冻结，不参与后续认知。

对应代码：[persona.py](file:///g:/generative_agents/reverie/backend_server/persona/persona.py#L236-L245)

### 6.3 快路径

如果：

- `planned_path` 还存在
- 不是新的一天
- 没有生理危机打断

则会走快路径：

- 可选做一次周期性社交扫描
- 然后直接 `execute(None)`

也就是说，快路径会跳过完整的 `plan` 和 `reflect`。

对应代码：[persona.py](file:///g:/generative_agents/reverie/backend_server/persona/persona.py#L258-L285)

### 6.4 生理危机打断

如果当前有活跃计划，但 `satiety` 或 `stamina` 已经低到阈值以下，则会：

1. 挂起当前动作
2. 记录中断原因
3. 清空当前动作
4. 清理社交状态
5. 进入完整认知链重规划

对应代码：[persona.py](file:///g:/generative_agents/reverie/backend_server/persona/persona.py#L287-L305)

配套逻辑在：

- [should_interrupt_for_physiological_crisis](file:///g:/generative_agents/reverie/backend_server/persona/memory_structures/scratch.py#L877-L892)
- [suspend_current_action](file:///g:/generative_agents/reverie/backend_server/persona/memory_structures/scratch.py#L998-L1016)
- [clear_current_action](file:///g:/generative_agents/reverie/backend_server/persona/memory_structures/scratch.py#L943-L958)

### 6.5 完整认知链

如果不走快路径，就执行：

```text
perceive -> retrieve -> plan -> reflect -> execute
```

对应代码：[persona.py](file:///g:/generative_agents/reverie/backend_server/persona/persona.py#L306-L342)

---

## 7. Perceive：空间更新 + 新事件入记忆

入口是 [perceive](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/perceive.py#L41-L245)。

### 7.1 空间感知

先扫描视野半径内的 tile，并把 world / sector / arena / object 写入 `s_mem.tree`。

对应代码：[perceive.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/perceive.py#L59-L87)

### 7.2 事件感知

只关注：

- 当前 arena 内的事件
- 最近的事件
- 不超过 `att_bandwidth`

对应代码：[perceive.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/perceive.py#L88-L122)

### 7.3 新事件入长期记忆

如果事件不在最近 `retention` 条记忆中，就会：

- 生成/复用 embedding
- 计算 poignancy
- 写入 `a_mem.add_event(...)`
- 某些对话场景还会写 `a_mem.add_chat(...)`
- 递减 `importance_trigger_curr`

对应代码：[perceive.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/perceive.py#L123-L217)

这一步的重要含义是：

- `perceive` 不只是“读世界”，还会直接改长期记忆
- `reflect` 是否触发，由这里累计的新事件重要性驱动

---

## 8. Retrieve：轻检索与重检索并存

### 8.1 主链里的轻检索

主链 `move()` 调用的是 [retrieve](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/retrieve.py#L16-L46)。

它只基于“新感知事件”的三元组，去关联记忆中拿：

- 相关 event
- 相关 thought

这一步不做复杂排序，也不打 embedding。

### 8.2 反思和聊天里的重检索

更复杂的检索是 [new_retrieve](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/retrieve.py#L201-L279)。

它会综合：

- recency
- relevance
- importance

并且会为 focal point 计算 embedding 相似度。

这意味着：

- 主 step 常规规划用的是轻检索
- 反思与社交聊天用的是重检索
- 后续如果要优化性能或插 world model，应该区分这两类检索成本

---

## 9. Plan：当前最关键的压缩式联合决策层

入口是 [plan](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/plan.py#L2336-L2427)。

### 9.1 新的一天只做 identity revise

当前版本在新的一天时，只调用 `revise_identity(persona)`，不再走旧版那套刚性小时级长日程生成。

对应代码：[plan.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/plan.py#L2342-L2344)

### 9.2 动作恢复与需求驱动决策

如果：

- 当前动作完成
- 或当前没有动作

则：

1. 记录 `last_action_desc`
2. 优先尝试恢复挂起动作
3. 恢复不了就进入 `decide_demand_action()`

对应代码：[plan.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/plan.py#L2346-L2355)

### 9.3 社交反应是在 demand action 之后叠加的

`plan()` 不只是决定生存动作，也会在已有 `retrieved` 的前提下继续做：

- 选择社交 focus
- 判断是否 react
- 发起聊天或等待
- 清理聊天状态

对应代码：[plan.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/plan.py#L2356-L2427)

因此当前 `plan()` 的结构是：

```text
恢复或生成主动作
  -> 再判断是否插入社交反应
  -> 最终返回 scratch.act_address
```

---

## 10. decide_demand_action()：意图收窄、动作翻译、局部约束已被压在一起

这是当前后续改造最重要的文件之一：

- [decide_demand_action](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/plan.py#L1886-L2333)

### 10.1 这一步已经不是纯“意图阶段”

这一步当前同时在做：

1. 编译上下文
2. 调用决策流水线
3. 修正 action / target
4. 解析目标地址
5. 生成对象事件
6. 调 `scratch.add_new_action(...)`

也就是说，当前工程上原来的“两阶段”已经被压缩成了一段联合决策逻辑。

### 10.2 输入上下文构建

在调用 `_run_decision_pipeline(...)` 之前，会先构建：

- 已知对象列表
- 对象微状态
- cooperative/social context
- 当前时间文本
- 生理状态摘要
- 动态生理规则
- 上一动作摘要
- intent memory summary

对应代码：[plan.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/plan.py#L1912-L2023)

### 10.3 决策流水线输出

`_run_decision_pipeline(...)` 会直接返回：

- `thinking_text`
- `decision`
- timing meta
- cache signature

对应代码：[plan.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/plan.py#L2024-L2043)

### 10.4 决策后立即进入翻译与纠偏

拿到 `decision` 后，当前函数立即进行：

- action / target / detail / duration 提取
- `Consume -> Gather` 的约束纠偏
- 非法食物源 target 的 fallback
- skill id 归一化
- target address 解析
- object side-effect 生成
- `add_new_action(...)`

对应代码：

- 决策字段处理：[plan.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/plan.py#L2044-L2200)
- target 纠偏与 fallback：[plan.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/plan.py#L2088-L2145)
- 地址解析：[plan.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/plan.py#L2221-L2255)
- 动作写入：[plan.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/plan.py#L2284-L2333)

### 10.5 这一层的真实定位

当前最准确的说法不是：

- “先独立生成意图，再独立翻译动作”

而是：

- **通过规则约束收窄决策空间后，直接在一个压缩式联合层里生成动作并落到 `scratch`**

这对简单链路是高效的，但对高风险链路会让职责边界变模糊。

---

## 11. Reflect：延迟型记忆增殖层

入口是 [reflect](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/reflect.py#L173-L266)。

### 11.1 反思触发

当 `importance_trigger_curr <= 0` 且记忆流非空时，触发 `run_reflect()`。

对应代码：[reflect.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/reflect.py#L136-L186)

### 11.2 反思内部会走重检索

`run_reflect()` 会：

1. 生成 focal points
2. 调 `new_retrieve()`
3. 为每个 focal point 生成 thoughts
4. 写入 `a_mem.add_thought(...)`

对应代码：[reflect.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/reflect.py#L100-L133)

### 11.3 对话后还有额外反思

聊天结束时间命中时，还会写：

- planning thought
- memo thought

对应代码：[reflect.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/reflect.py#L191-L266)

所以 `reflect` 的真实作用不是“每步都总结”，而是：

- 在阈值触发时批量沉淀高层 thought
- 在聊天结束时补一轮社交后记忆

---

## 12. Execute：路径生成、失败反馈与到达分发

入口是 [execute](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/execute.py#L38-L412)。

### 12.1 act_path_set 决定是否重算路径

如果当前动作还没有路径，就根据 `plan / act_address` 生成 target tiles，并跑路径搜索。

对应代码：[execute.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/execute.py#L68-L218)

### 12.2 路找不到时的处理

找不到合法路径时，不是原地硬等，而是：

- 记录 `navigation_failure`
- 写入执行 debug log
- 清空当前动作

对应代码：[execute.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/execute.py#L221-L250)

这一步是当前系统里最明确的结构化失败反馈之一。

### 12.3 到达后的 skill 分发

当路径走完且 `act_path_set` 还有效时，会根据 `act_command.skill_id` 去 `SKILL_REGISTRY` 找 skill，并调用 `skill.on_arrive(...)`。

对应代码：[execute.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/execute.py#L288-L340)

### 12.4 skill_blocked 的处理

如果 skill 存在但不能执行，会：

- 记日志
- 清空当前动作与路径
- 等待下一 step 重决策

对应代码：[execute.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/execute.py#L341-L372)

这说明 `execute()` 当前已经是事实上的“最终执行守卫层”。

---

## 13. scratch：当前 step 控制中枢

当前整个 step 中最关键的单一事实来源不是 `plan` 返回值，而是 `scratch`。

关键入口包括：

- 生理危机打断：[scratch.py](file:///g:/generative_agents/reverie/backend_server/persona/memory_structures/scratch.py#L877-L892)
- 当前动作清空：[scratch.py](file:///g:/generative_agents/reverie/backend_server/persona/memory_structures/scratch.py#L943-L958)
- 导航失败记录：[scratch.py](file:///g:/generative_agents/reverie/backend_server/persona/memory_structures/scratch.py#L960-L995)
- 动作挂起：[scratch.py](file:///g:/generative_agents/reverie/backend_server/persona/memory_structures/scratch.py#L998-L1016)
- 动作恢复：[scratch.py](file:///g:/generative_agents/reverie/backend_server/persona/memory_structures/scratch.py#L1019-L1080)

当前 `scratch` 里承载了：

- 当前动作描述与地址
- 当前 skill/command
- 当前路径
- 最近检索记忆
- 聊天状态
- 挂起动作快照
- 导航失败
- 决策签名与稳定窗口

换句话说，当前 step 的所有中间控制状态，几乎都汇聚在 `scratch`。

---

## 14. Step 与前端、存档、落盘的关系

### 14.1 environment 的含义

`environment/<step>.json` 是前端当前位置上报，不是后端本步决策结果。

对应写入链路：

- Django `process_environment()`：[views.py](file:///g:/generative_agents/environment/frontend_server/translator/views.py#L937-L960)

### 14.2 movement 的含义

`movement/<step>.json` 是后端当前 step 决策后的 movement 输出。

对应写入链路：

- Django `api_post_movement()`：[views.py](file:///g:/generative_agents/environment/frontend_server/translator/views.py#L1163-L1196)
- 后端本地写文件：[reverie.py](file:///g:/generative_agents/reverie/backend_server/reverie.py#L772-L776)

### 14.3 存档关系

长期存档都在：

- `storage/<sim_code>/reverie/`
- `storage/<sim_code>/environment/`
- `storage/<sim_code>/movement/`
- `storage/<sim_code>/personas/`

相关入口：

- 存档根目录定义：[utils.py](file:///g:/generative_agents/reverie/backend_server/utils.py#L34-L40)
- 增量保存：[reverie.py](file:///g:/generative_agents/reverie/backend_server/reverie.py#L233-L270)
- persona 存档写入：[persona.py](file:///g:/generative_agents/reverie/backend_server/persona/persona.py#L45-L89)

---

## 15. 当前链路的真实工程形态

综合当前源码，可以把 step 链路概括为：

```text
主循环调度
  -> world sync
  -> 代谢更新
  -> persona.move()
       -> 快路径继续执行
       -> 或完整链 perceive -> retrieve -> plan -> reflect -> execute
            -> 其中 decide_demand_action() 已经把
               意图收窄 + 动作翻译 + 局部约束 + 地址解析
               压缩到同一层
       -> execute() 负责最终路径与 skill 执行守卫
```

因此，当前系统既不是：

- 纯单阶段 LLM 出动作

也不是：

- 严格分离的“意图阶段 + 翻译阶段”

而是：

- **一个以 `scratch` 为控制中枢、把部分两阶段压缩在 `decide_demand_action()` 里的混合流水线**

---

## 16. 下一步改造最值得关注的插点

如果后续要做 world model / action layer 改造，最值得先看的不是全局重写，而是以下几个明确插点。

### 16.1 `decide_demand_action()` 前

这里适合插入显式候选评估层，因为进入 `_run_decision_pipeline()` 之前已经拥有：

- 对象状态
- 生理状态
- cooperative context
- inventory
- 上一动作信息

### 16.2 `_run_decision_pipeline()` 后、`target_resolution` 前

这里适合把“联合决策结果”和“动作翻译”重新切开。

当前这两者耦合过深，出错时不容易判断究竟是：

- 意图错了
- target 错了
- address 错了
- 还是执行条件不满足

### 16.3 `execute()` 的失败反馈点

最干净的结构化失败点是：

- `path_not_found`
- `skill_blocked`
- `skill_missing`

这些点非常适合作为后续 invalid target、world model 反馈和约束学习的输入。

### 16.4 快路径

快路径当前对性能很重要，但也带来一个语义问题：

- 它会跳过完整 `plan/reflect`
- 仅做周期性社交扫描 + execute

如果未来要加强决策约束，需要明确快路径是否也要插轻量 world check，而不是只在完整链路里做。

---

## 17. 一句话总结

当前 step 运算链路的核心特征是：

**主循环先同步世界并更新生理状态，再并发执行 persona.move()；单 persona 在 `scratch` 控制下，要么走快路径继续旧计划，要么进入 `perceive -> retrieve -> plan -> reflect -> execute` 完整链，其中 `decide_demand_action()` 已经把意图收窄、动作翻译、局部约束和目标解析压缩到同一层，而 `execute()` 则承担最终路径与技能执行守卫。**

这也是后续改造时应优先从 `decide_demand_action()` 与 `execute()` 之间重新切清职责边界的原因。
