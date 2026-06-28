# Generative Agents — 每 Step 循环计算逻辑详解

> 本文档描述了游戏完成初始化后，`ReverieServer.start_server()` 主循环中**每一步 (step)** 具体执行的计算内容和逻辑流程。
>
> 源码入口：[reverie.py](reverie/backend_server/reverie.py) → `start_server()` 方法 (第 300 行)

---

## 目录

1. [总体架构概览](#1-总体架构概览)
2. [Step 主循环流程](#2-step-主循环流程)
3. [阶段一：环境状态同步](#3-阶段一环境状态同步)
4. [阶段二：用户交互注入](#4-阶段二用户交互注入)
5. [阶段三：游戏对象清理](#5-阶段三游戏对象清理)
6. [阶段四：Persona 位置同步](#6-阶段四persona-位置同步)
7. [阶段五：Persona 认知管线 (核心)](#7-阶段五persona-认知管线核心)
   - [5.1 快速路径优化](#51-快速路径优化)
   - [5.2 Perceive（感知）](#52-perceive感知)
   - [5.3 Retrieve（检索）](#53-retrieve检索)
   - [5.4 Plan（规划）](#54-plan规划)
   - [5.5 Reflect（反思）](#55-reflect反思)
   - [5.6 Execute（执行）](#56-execute执行)
8. [阶段六：运动数据输出](#8-阶段六运动数据输出)
9. [阶段七：时间推进与自动保存](#9-阶段七时间推进与自动保存)
10. [数据流总览图](#10-数据流总览图)
11. [关键数据结构](#11-关键数据结构)

---

## 1. 总体架构概览

```
┌─────────────────────────────────────────────────────┐
│                  ReverieServer                       │
│  ┌───────────┐  ┌──────┐  ┌────────────────────┐   │
│  │   Maze    │  │ Time │  │   Personas (dict)  │   │
│  │ (地图)    │  │ 管理  │  │  name → Persona    │   │
│  └───────────┘  └──────┘  └────────────────────┘   │
│                                 │                    │
│                    ┌────────────┼───────────┐        │
│                    ▼            ▼           ▼        │
│              ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│              │ Spatial   │ │Associat. │ │ Scratch  │ │
│              │ Memory    │ │ Memory   │ │ (短期)   │ │
│              └──────────┘ └──────────┘ └──────────┘ │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │         Cognitive Modules (认知模块)          │   │
│  │  Perceive → Retrieve → Plan → Reflect → Execute │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

每个 Persona 拥有三层记忆：
- **Spatial Memory (空间记忆)**：树形结构，记录 Persona 了解的世界空间布局 (World → Sector → Arena → Game Object)
- **Associative Memory (联想记忆/记忆流)**：按时间排列的事件 (event)、想法 (thought)、对话 (chat) 节点序列，每个节点带有嵌入向量和重要性分数
- **Scratch (临时状态)**：当前行动描述、计划路径、日程表、当前事件、聊天状态等运行时状态

---

## 2. Step 主循环流程

```
start_server(int_counter)
│
├── while int_counter > 0:
│   ├── [检查前端聊天是否活跃，若活跃则暂停]
│   ├── 阶段一：获取环境状态 (从 Django API / 本地文件 / 内部追踪)
│   ├── 阶段二：获取并注入用户待处理操作 (聊天/指令)
│   ├── 阶段三：清理上一周期的游戏对象事件
│   ├── 阶段四：同步每个 Persona 的位置到后端地图
│   ├── 阶段五：【核心】并行调用每个 Persona 的 move() 认知管线
│   │   └── move() = Perceive → Retrieve → Plan → Reflect → Execute
│   ├── 阶段六：将运动结果写入文件并 POST 到 Django API
│   ├── 阶段七：step += 1，curr_time += sec_per_step，周期性自动保存
│   └── int_counter -= 1
│
└── sleep(server_sleep)
```

---

## 3. 阶段一：环境状态同步

**源码位置**：`reverie.py` 第 341-378 行

每一步开始时，后端需要知道所有 Persona 在前端的位置 (x, y 瓦片坐标)。获取方式按优先级：

| 优先级 | 方式 | 说明 |
|--------|------|------|
| 1 | Django HTTP API | `GET /api/get_environment/?sim_code=...&step=...` |
| 2 | 本地环境文件 | `{sim_folder}/environment/{step}.json` |
| 3 | 后端内部追踪 | 使用 `self.personas_tile` 字典中记录的上一步位置 |

**当浏览器关闭/刷新时**，后端可以完全独立运行（使用方式 3），实现了前后端解耦。

---

## 4. 阶段二：用户交互注入

**源码位置**：`reverie.py` 第 381-409 行

后端通过 `GET /api/get_pending_actions/` 拉取用户在前端发起的待处理操作：

- **chat（聊天）**：用户通过前端对某个 Persona 发送消息 → 以 whisper 形式注入 Persona 记忆
- **instruction（指令）**：用户给 Persona 的任务指令 → 以 `"Task instruction from user: ..."` 格式注入

注入实现调用 `load_history_via_whisper()`，该函数：
1. 调用 LLM 生成 Persona 对 whisper 的内心想法 (`generate_inner_thought`)
2. 为想法生成事件三元组 (`generate_action_event_triple`)
3. 计算重要性分数 (`generate_poig_score`)
4. 计算嵌入向量 (`get_embedding`)
5. 将想法存入联想记忆 (`a_mem.add_thought`)

处理完成后，向 Django 发送已处理的 action ID 确认。

---

## 5. 阶段三：游戏对象清理

**源码位置**：`reverie.py` 第 411-417 行

当 Persona 到达目标游戏对象（如床、电脑）并执行动作时，会给该对象添加特定事件描述（例如 `('bed', 'is', 'unmade', 'unmade')`）。

在每个新的 step 开始前，需要将上一周期添加的对象事件恢复为空白状态 `(object, None, None, None)`，以便本周期重新设置。

```python
for key, val in game_obj_cleanup.items():
    self.maze.turn_event_from_tile_idle(key, val)
game_obj_cleanup = dict()  # 重新初始化
```

---

## 6. 阶段四：Persona 位置同步

**源码位置**：`reverie.py` 第 419-448 行

对每个 Persona 执行以下操作：

1. **读取前后位置**：`curr_tile`（上一步位置）和 `new_tile`（从环境状态获取的当前位置）
2. **更新后端瓦片地图**：
   - 从旧瓦片移除 Persona 的主体事件
   - 在新瓦片添加 Persona 的主体事件
3. **处理到达目标的情况**：
   - 如果 Persona 的 `planned_path` 为空（即已到达目的地），则：
     - 在当前瓦片添加**对象动作事件**（如 "cooking on the stove"）
     - 移除该对象原来的空白事件
     - 将对象事件记录到 `game_obj_cleanup`，以便下一周期清理

---

## 7. 阶段五：Persona 认知管线（核心）

**源码位置**：`reverie.py` 第 454-478 行，`persona.py` 第 185-237 行

这是整个模拟的核心。每个 Persona 调用 `move()` 方法，执行完整的认知管线。

**并行优化**：所有 Persona 的 `move()` 通过 `ThreadPoolExecutor` 并行执行，每个 Persona 一个线程。

```python
def move(self, maze, personas, curr_tile, curr_time):
    # 1. 更新当前位置和时间
    self.scratch.curr_tile = curr_tile
    
    # 2. 判断是否是新的一天
    new_day = False / "First day" / "New day"
    self.scratch.curr_time = curr_time
    
    # 3. 快速路径：如果正在走路且不是新一天，跳过认知管线
    if self.scratch.planned_path and not new_day:
        return self.execute(maze, personas, None)
    
    # 4. 完整认知管线
    perceived = self.perceive(maze)
    retrieved = self.retrieve(perceived)
    plan = self.plan(maze, personas, new_day, retrieved)
    self.reflect()
    
    return self.execute(maze, personas, plan)
```

### 5.1 快速路径优化

**源码位置**：`persona.py` 第 222-223 行

当 Persona 正在沿路径行走（`planned_path` 非空）且不是新的一天时，直接跳过感知-检索-规划-反思的完整管线，只执行 Execute 步骤取出路径中的下一个瓦片。这大幅减少了不必要的 LLM 调用。

---

### 5.2 Perceive（感知）

**源码文件**：[perceive.py](reverie/backend_server/persona/cognitive_modules/perceive.py)

感知模块负责扫描 Persona 周围的环境，发现新事件并存入记忆。

#### 流程：

```
Perceive
├── 1. 感知空间 (Perceive Space)
│   ├── 获取视野范围内的瓦片 (vision_r 半径)
│   └── 更新空间记忆树 (s_mem): World → Sector → Arena → Game Object
│
├── 2. 感知事件 (Perceive Events)
│   ├── 收集同一区域 (arena) 内所有瓦片上的事件
│   ├── 按距离排序
│   ├── 取最近的 att_bandwidth 个事件
│   └── 去重 (同一事件可能跨多个瓦片)
│
└── 3. 存储新事件
    ├── 对每个感知到的事件:
    │   ├── 检查是否在最近 retention 条记忆中已存在
    │   ├── 如果是新事件:
    │   │   ├── 提取关键词 (subject, object)
    │   │   ├── 计算/获取嵌入向量 (embedding)
    │   │   ├── 【LLM调用】计算重要性分数 (poignancy score, 1-10)
    │   │   ├── 如果是对话事件，额外创建 chat 节点
    │   │   ├── 将事件添加到联想记忆 (a_mem.add_event)
    │   │   └── 更新反思触发计数器 (importance_trigger_curr)
    │   └── 返回新增的 ConceptNode 列表
```

**关键超参数**：
| 参数 | 含义 |
|------|------|
| `vision_r` | 视野半径（瓦片数） |
| `att_bandwidth` | 注意力带宽，最多同时感知的事件数 |
| `retention` | 保留窗口，最近 N 条记忆内的事件不重复感知 |

**重要性分数 (Poignancy Score)**：
- 通过 LLM 对事件描述评分 (1-10)
- "is idle" 事件直接返回 1 (无需 LLM)
- 带有内存缓存，相同 persona+事件描述 不重复调用 LLM

---

### 5.3 Retrieve（检索）

**源码文件**：[retrieve.py](reverie/backend_server/persona/cognitive_modules/retrieve.py)

检索模块根据感知到的新事件，从联想记忆中提取相关的历史事件和想法，为规划提供上下文。

#### 流程：

```
Retrieve
├── 输入: perceived (新感知到的 ConceptNode 列表)
├── 对每个感知事件:
│   ├── 检索相关事件: a_mem.retrieve_relevant_events(s, p, o)
│   └── 检索相关想法: a_mem.retrieve_relevant_thoughts(s, p, o)
└── 输出: retrieved 字典
    └── { event_description: {
            "curr_event": ConceptNode,
            "events": [ConceptNode, ...],
            "thoughts": [ConceptNode, ...]
         }}
```

#### `new_retrieve()` — 高级检索（用于反思和对话）

在反思和对话场景中使用更复杂的检索算法，综合三个维度评分：

```
最终分数 = recency_w × recency × 0.5
         + relevance_w × relevance × 3
         + importance_w × importance × 2
```

| 维度 | 计算方式 | 作用 |
|------|---------|------|
| **Recency (时近性)** | 指数衰减：`recency_decay ^ i`，i 为时间顺序 | 越近的记忆得分越高 |
| **Importance (重要性)** | 使用记忆节点的 poignancy 分数 | 重要事件优先 |
| **Relevance (相关性)** | 嵌入向量余弦相似度 `cos_sim(node_embedding, focal_embedding)` | 与当前焦点语义相关的优先 |

所有维度先归一化到 [0, 1]，再加权求和。取 top-N 个节点返回。

---

### 5.4 Plan（规划）

**源码文件**：[plan.py](reverie/backend_server/persona/cognitive_modules/plan.py)

规划模块是最复杂的认知模块，包含长期规划、短期行动决策和社交反应三个层次。

#### 5.4.1 PART 1：长期规划 (新一天时触发)

```
_long_term_planning(persona, new_day)
│
├── 1. 生成起床时间
│   └── 【LLM调用】run_gpt_prompt_wake_up_hour → 整数小时 (e.g., 8)
│
├── 2. 生成日计划
│   ├── "First day": 【LLM调用】generate_first_daily_plan
│   │   └── 产出: ["wake up at 6:00 am", "eat breakfast at 7:00 am", ...]
│   └── "New day": revise_identity (基于过去事件修正身份和每日计划)
│       ├── 【LLM调用】检索相关记忆，生成 plan_note
│       ├── 【LLM调用】生成 thought_note (对过去几天的情感总结)
│       ├── 【LLM调用】更新 currently 状态
│       └── 【LLM调用】生成新的 daily_plan_req
│
├── 3. 生成小时级日程表
│   └── 【LLM调用】generate_hourly_schedule → [['sleeping', 360], ['routine', 60], ...]
│
└── 4. 将日计划写入联想记忆 (作为 thought 节点)
```

#### 5.4.2 PART 2：确定当前行动 (当前动作结束时触发)

```
_determine_action(persona, maze)
│
├── 1. 获取当前日程索引 (curr_index)
│
├── 2. 任务分解 (Decompose)
│   ├── 将 ≥60 分钟的大任务分解为小步骤
│   │   └── 【LLM调用】generate_task_decomp
│   │       e.g., "morning routine (60min)" →
│   │             [['going to bathroom', 5], ['getting dressed', 5], ...]
│   └── 提前分解未来 1 小时的任务（预分解）
│
├── 3. 确定行动地点
│   ├── 【LLM调用】generate_action_sector → 目标区块 (e.g., "the Ville")
│   ├── 【LLM调用】generate_action_arena → 目标场地 (e.g., "bedroom 2")
│   └── 【LLM调用】generate_action_game_object → 目标对象 (e.g., "bed")
│       → 最终地址: "world:sector:arena:game_object"
│
├── 4. 生成行动元数据
│   ├── 【LLM调用】generate_action_pronunciatio → 表情符号 (e.g., "💤")
│   ├── 【LLM调用】generate_action_event_triple → (s, p, o) 三元组
│   ├── 【LLM调用】generate_act_obj_desc → 对象描述
│   └── 【LLM调用】generate_act_obj_event_triple → 对象事件三元组
│
└── 5. 写入 scratch: persona.scratch.add_new_action(...)
```

#### 5.4.3 PART 3：社交反应（感知到其他 Persona 时触发）

```
社交反应流程
│
├── 1. _choose_retrieved: 从多个感知事件中选择一个焦点事件
│   ├── 优先选择其他 Persona 的事件（排除自己的事件）
│   └── 跳过 "is idle" 事件
│
├── 2. _should_react: 决定反应模式
│   ├── lets_talk → "chat with {name}" (发起对话)
│   │   ├── 前置条件检查: 非睡眠、非23点、非等待、非正在聊天
│   │   ├── 检查聊天缓冲 (避免连续重复聊天)
│   │   └── 【LLM调用】generate_decide_to_talk → yes/no
│   │
│   ├── lets_react → "wait: {until_time}" (等待反应)
│   │   ├── 前置条件检查: 正在路径上、同一地点
│   │   └── 【LLM调用】generate_decide_to_react → "1"(等待)/"2"(忽略)
│   │
│   └── False (不反应)
│
├── 3. 执行反应
│   ├── _chat_react: 生成对话
│   │   ├── 【LLM调用×多轮】agent_chat_v2 (迭代式对话，最多8轮)
│   │   │   └── 每轮: 检索记忆 → 总结关系 → 生成单句 → 判断结束
│   │   ├── 【LLM调用】生成对话摘要
│   │   ├── 修改双方日程表 (generate_new_decomp_schedule)
│   │   └── 设置双方的聊天状态和聊天缓冲
│   │
│   └── _wait_react: 设置等待状态
│       └── 修改日程表，插入等待动作
│
└── 4. 聊天状态清理
    ├── 如果当前不在聊天，清除聊天相关状态
    └── 聊天缓冲计数器递减 (防止立即再次聊天)
```

---

### 5.5 Reflect（反思）

**源码文件**：[reflect.py](reverie/backend_server/persona/cognitive_modules/reflect.py)

反思模块让 Persona 回顾记忆，产生高层次的洞察和想法。

#### 触发条件

```python
def reflection_trigger(persona):
    # 当累积的新事件重要性分数超过阈值时触发
    if importance_trigger_curr <= 0 and 记忆非空:
        return True
```

- `importance_trigger_curr` 初始值 = `importance_trigger_max`（超参数，如 150）
- 每次感知新事件时，`importance_trigger_curr -= event_poignancy`
- 当累积重要性足够多（触发器降到 0 或以下）时触发反思

#### 反思流程

```
reflect(persona)
│
├── 1. 检查触发条件 (reflection_trigger)
│   └── importance_trigger_curr <= 0?
│
├── 2. 如果触发:
│   ├── run_reflect:
│   │   ├── 【LLM调用】generate_focal_points → 3个焦点 (基于最近记忆)
│   │   ├── new_retrieve → 对每个焦点检索相关记忆
│   │   └── 对每个焦点的检索结果:
│   │       ├── 【LLM调用】generate_insights_and_evidence → 5个洞察+证据
│   │       └── 将每个洞察存入联想记忆 (a_mem.add_thought)
│   │           ├── 【LLM调用】生成事件三元组
│   │           ├── 【LLM调用】计算重要性分数
│   │           └── 计算嵌入向量
│   │
│   └── reset_reflection_counter:
│       ├── importance_trigger_curr = importance_trigger_max
│       └── importance_ele_n = 0
│
└── 3. 对话结束处理 (chatting_end_time 到达时)
    ├── 【LLM调用】generate_planning_thought_on_convo → 对话后的计划想法
    ├── 存入联想记忆
    ├── 【LLM调用】generate_memo_on_convo → 对话备忘录
    └── 存入联想记忆
```

---

### 5.6 Execute（执行）

**源码文件**：[execute.py](reverie/backend_server/persona/cognitive_modules/execute.py)

执行模块将规划的行动地址转化为具体的移动路径和下一步瓦片坐标。

#### 流程

```
execute(persona, maze, personas, plan)
│
├── 1. 判断是否需要计算新路径 (act_path_set == False?)
│   │
│   ├── plan 包含 "<persona>": 走向另一个 Persona
│   │   └── 计算目标 Persona 的位置，寻路到中间点
│   │
│   ├── plan 包含 "<waiting>": 等待状态
│   │   └── 目标瓦片 = 当前位置
│   │
│   ├── plan 包含 "<random>": 随机位置
│   │   └── 从地址对应的瓦片中随机选一个
│   │
│   └── 默认: 寻路到 plan 指定的地点
│       ├── 从 maze.address_tiles[plan] 获取候选瓦片
│       ├── 随机采样 ≤4 个候选
│       ├── 过滤掉已被其他 Persona 占据的瓦片
│       └── A* 寻路到最近的候选瓦片
│
├── 2. 设置 planned_path 和 act_path_set = True
│
└── 3. 取出下一步
    ├── 如果 planned_path 非空: 弹出第一个瓦片
    ├── 否则: 留在当前位置
    └── 返回 (next_tile, pronunciatio, description)
```

**路径查找**使用 `path_finder()` 函数（基于 A* 算法），输入碰撞地图 (`collision_maze`) 和起终点，输出瓦片坐标路径。

---

## 8. 阶段六：运动数据输出

**源码位置**：`reverie.py` 第 480-504 行

所有 Persona 的 `move()` 返回结果汇总为 `movements` 字典：

```json
{
  "persona": {
    "Isabella Rodriguez": {
      "movement": [58, 9],
      "pronunciatio": "💬",
      "description": "chatting with Maria Lopez @ cafe:main room:table",
      "chat": [["Isabella", "Hi!"], ["Maria", "Hello!"]]
    },
    "Klaus Mueller": {
      "movement": [38, 12],
      "pronunciatio": "📝",
      "description": "writing a research paper @ library:study room:desk",
      "chat": null
    }
  },
  "meta": {
    "curr_time": "February 13, 2023, 08:30:00"
  }
}
```

该数据同时：
1. **POST 到 Django API**：`/api/post_movement/`，供前端实时渲染
2. **写入本地文件**：`{sim_folder}/movement/{step}.json`，作为持久化记录

---

## 9. 阶段七：代谢计算、时间推进与自动保存

**源码位置**：`reverie.py` 第 506-535 行

### 9.1 生理代谢衰减计算
在每个时间步推进前，系统遍历所有智能体计算其生理代谢状态的变化：
*   **精力值 (Stamina) 计算**：
    *   若在休眠 (`sleeping`)，每步恢复 `2.0`。
    *   若在休息 (`resting` / `idling`)，每步恢复 `1.5`。
    *   若在移动中（且 `planned_path` 非空），每步消耗 `1.0`。
    *   若执行常规活动，每步消耗 `0.5`。
*   **饱食度 (Satiety) 计算**：
    *   休眠中每步降低 `0.2`。
    *   休息中每步降低 `0.3`
    *   其他日常行为下，饱食度每步匀速降低 `0.5`。
*   **生命值 (Health) 与饥饿惩罚**：
    *   若饱食度降为 `0.0`，开始产生饥饿惩罚，每步健康值 `health` 扣除 `2.0`。
*   **数据交换对齐**：智能体的实时饱食度、精力、健康和背包数据将自动写入外部 step 行动记录 JSON 文件。

### 9.2 时间推移与自动保存
```python
self.step += 1
self.curr_time += datetime.timedelta(seconds=self.sec_per_step)

# 每 10 步自动保存
if self.step % 10 == 0:
    self.save()
```

- `sec_per_step` 默认为 10 秒（游戏内时间），即每 step 推进 10 秒
- 自动保存调用 `save()` 方法，保存：
  - Reverie 元信息 (`meta.json`)
  - 所有 Persona 的三层记忆，包括新引入的生理状态与背包技能数据
  - LLM 提示词缓存 (`save_cache_to_disk()`)

---

## 10. 数据流总览图

```
                          ┌─────────────────────┐
                          │   Frontend (浏览器)   │
                          └──────┬───────────────┘
                                 │ HTTP API
                          ┌──────▼───────────────┐
                          │   Django Server       │
                          │   (环境/运动/操作)      │
                          └──────┬───────────────┘
                                 │
                 ┌───────────────▼───────────────┐
                 │     ReverieServer.start_server │
                 │         每 Step 循环            │
                 └───────────────┬───────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
     ┌────▼─────┐          ┌────▼─────┐          ┌────▼─────┐
     │ Persona A │          │ Persona B │          │ Persona C │
     │  move()   │          │  move()   │          │  move()   │
     └────┬─────┘          └────┬─────┘          └────┬─────┘
          │ (并行线程)           │                      │
     ┌────▼────────────────────────────────────────────┐
     │            认知管线 (每个 Persona)                 │
     │                                                  │
     │  ┌──────────┐   ┌──────────┐   ┌──────────┐    │
     │  │ Perceive │──▶│ Retrieve │──▶│   Plan   │    │
     │  │ 感知环境  │   │ 检索记忆  │   │ 规划行动  │    │
     │  └──────────┘   └──────────┘   └────┬─────┘    │
     │                                     │           │
     │                               ┌─────▼─────┐    │
     │                               │  Reflect  │    │
     │                               │  反思总结   │    │
     │                               └─────┬─────┘    │
     │                                     │           │
     │                               ┌─────▼─────┐    │
     │                               │  Execute  │    │
     │                               │  执行移动   │    │
     │                               └───────────┘    │
     └─────────────────────────────────────────────────┘
                          │
                          ▼
              (next_tile, emoji, description)
```

---

## 11. 关键数据结构

### ConceptNode (联想记忆节点)

```
ConceptNode
├── node_id: 唯一标识
├── node_type: "event" / "thought" / "chat"
├── created: 创建时间
├── expiration: 过期时间
├── last_accessed: 最后访问时间
├── subject, predicate, object: 事件三元组 (s, p, o)
├── description: 描述文本
├── embedding_key: 嵌入向量的键
├── poignancy: 重要性分数 (1-10)
├── keywords: 关键词集合
├── filling: 对话内容 (仅 chat 类型)
└── evidence: 证据节点 ID 列表 (仅 thought 类型)
```

### Scratch (临时状态) 关键字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `curr_tile` | tuple | 当前瓦片坐标 (x, y) |
| `curr_time` | datetime | 当前游戏时间 |
| `daily_req` | list[str] | 日计划 (粗粒度) |
| `f_daily_schedule` | list[list] | 细化日程 [['task', minutes], ...] |
| `act_address` | str | 当前动作地址 "world:sector:arena:object" |
| `act_description` | str | 当前动作描述 |
| `act_pronunciatio` | str | 当前动作表情符号 |
| `act_event` | tuple | 当前事件三元组 (s, p, o) |
| `act_duration` | int | 动作持续时间（分钟） |
| `act_start_time` | datetime | 动作开始时间 |
| `planned_path` | list[tuple] | 计划移动路径 |
| `act_path_set` | bool | 路径是否已设定 |
| `chatting_with` | str | 正在聊天的对象名 |
| `chat` | list | 当前对话内容 |
| `chatting_with_buffer` | dict | 聊天冷却缓冲 {name: countdown} |
| `chatting_end_time` | datetime | 聊天结束时间 |
| `importance_trigger_curr` | float | 反思触发计数器（当前值） |
| `importance_trigger_max` | float | 反思触发阈值 |
| `vision_r` | int | 视野半径 |
| `att_bandwidth` | int | 注意力带宽 |
| `retention` | int | 记忆保留窗口 |
| `recency_decay` | float | 时近性衰减因子 |
| `satiety` | float | 生理饱食度 (0.0 - 100.0) |
| `stamina` | float | 生理精力值 (0.0 - 100.0) |
| `health` | float | 生理生命健康值 (0.0 - 100.0) |
| `inventory` | dict | 背包物品 {item_name: quantity} |
| `skills` | dict | 技能等级与经验值数据槽 |
| `personal_knowledge` | dict | 个人专有知识库 |
| `survival_applied` | bool | 生存交互效果是否已应用标志 |

---

## 附：每 Step 的 LLM 调用次数估算

| 场景 | LLM 调用次数 (每 Persona) |
|------|--------------------------|
| 快速路径 (mid-walk) | **0 次** (生理危机除外，若打断则调用生存决策) |
| 生理危机重规划 (ReAct) | **1 次** (触发决定生存动作 `decide_survival_action`) |
| 普通 Step (无新事件) | 0 次 (感知无新事件则跳过) |
| 感知到新事件 | 1-N 次 (poignancy 评分，有缓存) |
| 确定新动作 | ~8-10 次 (分解+选地点+元数据) |
| 新的一天 | ~30+ 次 (日计划+小时日程+任务分解) |
| 触发反思 | ~15-20 次 (焦点+检索+洞察) |
| 发起对话 | ~20-40 次 (多轮对话+摘要+日程修改) |

> **优化策略**：通过快速路径跳过、poignancy 缓存、prompt 磁盘缓存 (`save_cache_to_disk()`) 等机制大幅减少 LLM 调用次数。

---

## 性能瓶颈分析与加速方案

### 当前硬件与模型环境

| 项目 | 当前配置 |
|------|---------|
| **GPU** | GTX 1070 Ti 8GB (Pascal 架构, Compute 6.1, 无 Tensor Core) |
| **显存占用** | 已用 ~6.7 GB / 总 8 GB |
| **对话模型** | `qwen2.5:7b` (4.7 GB, gpt35 和 gpt4 均使用同一模型) |
| **Embedding 模型** | `nomic-embed-text` (274 MB) |
| **推理框架** | Ollama 本地推理 |
| **配置文件** | `reverie/backend_server/utils.py` |

### 核心瓶颈定位（按严重程度排序）

#### 🔴 瓶颈 1：LLM 串行调用次数过多

`persona.py` 中认知管线是完全串行的：

```
perceived = self.perceive(maze)      # 可能调用 N 次 LLM (poignancy 评分)
retrieved = self.retrieve(perceived)  # 无 LLM，但依赖 perceive 结果
plan      = self.plan(...)           # 可能调用 10-40 次 LLM
self.reflect()                       # 可能调用 15-20 次 LLM
```

一次「确定新动作」(`_determine_action`) 需要 ~8-10 次串行 LLM 调用：任务分解 + 选区块 + 选场地 + 选对象 + 生成表情 + 生成三元组 × 2 + 对象描述。

#### 🔴 瓶颈 2：对话生成是 LLM 调用爆炸区

`converse.py` 中 `agent_chat_v2` 最多 8 轮对话，每轮需要：
- `new_retrieve()` → 含 embedding 计算
- `generate_summarize_agent_relationship()` → 1 次 LLM
- `generate_one_utterance()` → 1 次 LLM

一次完整对话 = ~20-40 次 LLM 调用，且全部串行。

#### 🟡 瓶颈 3：GPU 硬件限制

GTX 1070 Ti 是 2016 年 Pascal 架构，**没有 Tensor Core**，FP16 推理加速有限。7B 模型已经是这张卡能跑的极限，且显存几乎占满，无法增大 KV cache batch size。

#### 🟡 瓶颈 4：Persona 并行受 GPU 并发限制

`reverie.py` 中虽然使用了 `ThreadPoolExecutor` 并行调用各 Persona 的 `move()`，但本地 Ollama 使用单张 GPU，多线程并发请求实际是在 GPU 层排队，无法真正并行。

#### 🟡 瓶颈 5：反思连锁 LLM 调用

反思触发时：3 个焦点 × (检索 + 5 个洞察 × (三元组 + 评分 + embedding)) ≈ 15-20 次 LLM。

#### 🟡 瓶颈 6：「新的一天」是最慢的单步

`_long_term_planning` 在新一天触发时：起床时间 → 日计划 → 24 小时逐小时日程生成（每小时 1 次 LLM，且有 diversity_repeat 循环最多 3 次）→ 任务分解。一个 Persona 新一天 = 30+ 次 LLM 调用。

#### 🟢 已有的优化措施

| 优化 | 位置 | 效果 |
|------|------|------|
| 快速路径跳过 | `persona.py:222` | mid-walk 时 0 次 LLM 调用 |
| Poignancy 内存缓存 | `perceive.py:17` | 相同 persona+事件描述不重复评分 |
| Prompt 磁盘缓存 | `gpt_structure.py` | 完全相同 prompt 直接返回缓存 |
| Embedding 内存缓存 | `gpt_structure.py:394` | 相同文本不重复计算嵌入 |
| Embedding 批量接口 | `gpt_structure.py:424` | `get_embeddings_batch` 合并请求 |
| 前端聊天时暂停后端 | `reverie.py:333` | 避免 Ollama 资源争抢 |

---

### 方案一：软件层优化 — 换更小模型 + 分级策略（免费，立即可做）

#### 1a. 替换为更小更快的模型

Generative Agents 的大部分 prompt 并不复杂（评分 1-10、选地点、生成表情符号），3B 模型完全够用。只有对话生成和反思洞察需要较强的语言能力。

```bash
# 拉取小模型
ollama pull qwen2.5:3b
```

修改 `reverie/backend_server/utils.py`：

```python
# 当前配置（两者相同，浪费了分级设计）
gpt35_model = "qwen2.5:7b"
gpt4_model = "qwen2.5:7b"

# 推荐：分级策略 — 简单任务用小模型，复杂任务保持大模型
gpt35_model = "qwen2.5:3b"    # 简单任务：评分、选地点、表情符号、三元组
gpt4_model  = "qwen2.5:7b"    # 复杂任务：对话、反思、日计划
```

代码中 `gpt35_model` 和 `gpt4_model` 的调用分工：
- `GPT_request` / `ChatGPT_request` / `ChatGPT_single_request` → 使用 `gpt35_model` → 大量简单任务
- `GPT4_request` → 使用 `gpt4_model` → 少量复杂任务

其他可选小模型：

| 模型 | 大小 | 特点 |
|------|------|------|
| `qwen2.5:3b` | ~2 GB | 中文能力强，推荐首选 |
| `phi3:3.8b` | ~2.3 GB | 微软出品，推理能力好 |
| `gemma2:2b` | ~1.7 GB | Google 出品，最轻量 |

**预期效果**：简单任务速度提升 ~2x，显存占用下降。

#### 1b. 使用更激进的量化版本

```bash
ollama pull qwen2.5:7b-instruct-q4_0   # Q4 量化，更小更快
ollama pull qwen2.5:3b-instruct-q4_0   # 3B + Q4，极速
```

Q4 量化可以再减少 ~30% 推理时间和显存占用，精度损失对本项目的 prompt 几乎无影响。

#### 1c. 限制 max_tokens 输出长度

在 `gpt_structure.py` 中，`ChatGPT_single_request` 和 `ChatGPT_request` 没有设置 `max_tokens`，默认可能生成很长输出。大部分任务只需要几个词到一段话：

```python
# gpt_structure.py — ChatGPT_single_request / ChatGPT_request
completion = openai.ChatCompletion.create(
    model=gpt35_model,
    messages=[...],
    max_tokens=256,  # 添加输出长度限制
)
```

**预期效果**：减少不必要的 token 生成，提速 10-30%。

---

### 方案二：升级 GPU（硬件方案，性价比推荐）

| GPU | 显存 | 相对 1070Ti 速度 | 参考价(二手) | 推荐运行模型 |
|-----|------|-----------------|-------------|-------------|
| **RTX 3060 12GB** | 12 GB | ~3-4x | ~¥1200 | qwen2.5:7b 流畅 |
| **RTX 3090** | 24 GB | ~6-8x | ~¥3500 | qwen2.5:14b 可跑 |
| **RTX 4060 Ti 16GB** | 16 GB | ~5-6x | ~¥2800 | qwen2.5:7b 极速 |
| **RTX 4090** | 24 GB | ~10-15x | ~¥12000 | qwen2.5:32b 可跑 |

速度提升来源：
- **Tensor Core**：RTX 30/40 系列有 Tensor Core，FP16 推理快数倍（1070 Ti 没有）
- **更大显存**：可以使用更大 KV cache batch size，减少显存换页
- **更高显存带宽**：LLM 推理主要瓶颈是显存带宽（1070Ti: 256 GB/s → 3060: 360 GB/s → 3090: 936 GB/s）

**性价比首选**：二手 **RTX 3060 12GB** — 花 ~¥1200 获得 3-4 倍速度提升 + 显存从 8GB→12GB。

---

### 方案三：云端 API 混合推理（最快见效）

代码中已预留 DeepSeek 云端配置，取消注释即可切换：

```python
# reverie/backend_server/utils.py
# 方式 A：全量切换到云端
openai_api_key = "sk-f7775909e210487eb449ee89cef77126"
openai_api_base = "https://api.deepseek.com/v1"
gpt35_model = "deepseek-chat"
gpt4_model = "deepseek-chat"
```

| 对比项 | 本地 Ollama qwen2.5:7b | DeepSeek API |
|--------|------------------------|--------------|
| 单次延迟 | 2-8 秒 | **0.3-1 秒** |
| 并发能力 | 1 (GPU 争抢) | **多路并发** |
| 模型质量 | 7B 模型 | **等效 200B+** |
| 每次成本 | 电费 | ~¥0.001/次 |
| 一天模拟成本 (~5000次) | 电费 | **~¥5** |
| 网络依赖 | 无 | 需要互联网 |

**混合策略**（推荐）：简单任务本地 3B 快速推理，复杂对话/反思用云端 API：

```python
# 混合配置示例
openai_api_key = "ollama"
openai_api_base = "http://localhost:11434/v1"
gpt35_model = "qwen2.5:3b"           # 简单任务本地快速跑

# gpt4_model 单独指向云端 — 需要修改 GPT4_request 函数
# 在 gpt_structure.py 的 GPT4_request 中单独设置 api_base 和 api_key
```

> **注意**：混合策略需要小幅修改 `GPT4_request()` 函数，使其独立使用云端 API 配置。

---

### 方案四：推理框架替换（进阶）

如果坚持本地推理且升级了 GPU，可以将 Ollama 换成更快的推理引擎：

| 框架 | 相对 Ollama 速度 | 优势 | 硬件要求 |
|------|-----------------|------|---------|
| **llama.cpp server** | ~1.2x | 内存效率更高，直接替代 Ollama | 任意 GPU |
| **vLLM** | ~2-3x | PagedAttention，支持真正的并发 batch | RTX 30/40 系列 |
| **TensorRT-LLM** | ~2-4x | NVIDIA 官方优化，极致性能 | RTX 30/40 系列 |

> 在 GTX 1070 Ti 上，框架优化的提升有限（~10-20%），因为硬件本身是瓶颈。建议先升级 GPU 再考虑换框架。

vLLM 安装与替代 Ollama 的方式（需 RTX 30+）：

```bash
pip install vllm
# 启动兼容 OpenAI API 的服务
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-7B-Instruct \
    --port 11434 \
    --api-key ollama
```

然后 `utils.py` 无需修改，因为 API 接口兼容。

---

### 🏆 推荐实施顺序

| 优先级 | 方案 | 改动量 | 预期效果 | 成本 |
|--------|------|--------|---------|------|
| **① 立即做** | 换 `qwen2.5:3b` + 分级模型 | 改 `utils.py` 1 行 | **提速 ~2x** | 免费 |
| **② 立即做** | 加 `max_tokens=256` 限制 | 改 `gpt_structure.py` 几行 | **提速 10-30%** | 免费 |
| **③ 按需** | 切回 DeepSeek API (全量或混合) | 改 `utils.py` 1 行 | **提速 5-10x** | ~¥5/天 |
| **④ 长期** | 升级到 RTX 3060 12GB | 换硬件 | **提速 3-4x** | ~¥1200 |
| **⑤ 进阶** | 换 vLLM 推理框架 | 安装+启动命令 | **提速 2-3x** | 需 RTX 30+ |

> **综合推荐**：先做 ① + ②（5 分钟内完成，免费提速 ~2.5x），再根据需要选择 ③ 或 ④。

### 量化效果估算

以「到达目的地 + 确定新动作」场景为例（~10 次 LLM 调用）：

| 配置 | 单次延迟 | 10 次总耗时 |
|------|---------|------------|
| 当前: 1070Ti + qwen2.5:7b | ~4 秒 | **~40 秒** |
| 方案①: 1070Ti + qwen2.5:3b(简单) + 7b(复杂) | ~2 秒 | **~20 秒** |
| 方案③: DeepSeek API | ~0.5 秒 | **~5 秒** |
| 方案④: RTX 3060 + qwen2.5:7b | ~1.2 秒 | **~12 秒** |
| 方案④+①: RTX 3060 + 分级模型 | ~0.8 秒 | **~8 秒** |
