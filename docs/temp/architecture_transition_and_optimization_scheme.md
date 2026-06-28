# Generative Agents — 架构过渡与优化实施方案

为了实现从现有社交模拟架构（参见 [core_architecture_guide.md](file:///g:/generative_agents/docs/core_architecture_guide.md)）向“生存与进化全要素沙盒”的顺利转变，且保证第一步“使现有项目跑通并稳定运行”，本方案设计了渐进式改造路径与优化落地细节。

---

## 1. 现有 baseline 跑通与稳定性修复

在进行生存和进化机制的侵入式改造前，必须首先确保当前小镇模拟能够使用本地模型（Ollama + Qwen 2.5）稳定、快速地运行。针对目前已知的崩溃点和瓶颈，执行以下首要修复：

### 1.1 空间记忆对齐与 KeyError 彻底防范
*   **问题**：后端在执行动作 [execute.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/execute.py) 与空间记忆 [spatial_memory.py](file:///g:/generative_agents/reverie/backend_server/persona/memory_structures/spatial_memory.py) 检索时，容易因为拼写大小写不一致或遗漏 `"the Ville:"` 前缀产生 `KeyError` 导致模拟中断。
*   **优化方案**：
    *   在 [spatial_memory.py](file:///g:/generative_agents/reverie/backend_server/persona/memory_structures/spatial_memory.py) 的 `ret_associated_nodes` 等寻路与地址查询函数中，对输入参数和字典 key 统一执行 `.strip().lower()` 预处理。
    *   增加模糊回退匹配：若找不到精确匹配，自动进行大小写不敏感的前缀匹配，并对 `"the Ville:"` 等地图前缀进行兼容清洗。

### 1.2 物理位置边界拦截器优化
*   **问题**：`execute.py` 中用于处理智能体相遇或协作的物理拦截逻辑过于提前。例如 Klaus 还在床上就被咖啡馆的 Isabella 服务逻辑拦截，导致陷入无限的 LLM 计算等待。
*   **优化方案**：
    *   在 [execute.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/execute.py) 的拦截条件中，加入严格的**距离或区域重合校验**。只有当两个智能体在物理坐标（X, Y 瓦片）均已到达咖啡馆（Cafe）指定竞技场（Arena）范围内时，才激活协作等待状态。

### 1.3 LLM 输出格式约束与解析器增强
*   **问题**：本地开源模型（如 `qwen2.5:7b`）在生成 JSON 响应或特定格式列表时，偶尔会携带 Markdown 标签（如 ```json ... ```）或多余的解释性文本，导致解析代码崩溃。
*   **优化方案**：
    *   在 [gpt_structure.py](file:///g:/generative_agents/reverie/backend_server/persona/prompt_template/gpt_structure.py) 的解析逻辑中，加入正则表达式清洗器。自动剔除首尾的 Markdown 标记以及非标准 JSON 字符，再进行 `json.loads` 反序列化。
    *   在 Prompt 模版末尾强制追加统一的指令后缀：`"Respond ONLY in valid raw JSON format. Do not include markdown code block wrapper."`。

---

## 2. 渐进式转变设计：三步走过渡路线

在保障 Baseline 稳定运行的基础上，采用“数据挂载 $\rightarrow$ 逻辑中断 $\rightarrow$ 动态反馈”的三步走策略，将系统向生存与进化架构推进。

```
                    ┌──────────────────────────────┐
                    │  第一步：数据槽被动挂载      │
                    │  (Scratch 变量与 JSON 对齐)  │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │  第二步：反应式 ReAct 决策   │
                    │  (打断机制与 GPT 生存规划)   │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │  第三步：技能/知识库生效     │
                    │  (动作判定与书籍读写学习)   │
                    └──────────────────────────────┘
```

### 2.1 第一步：数据槽被动挂载（无痛引入数值）
本阶段只修改内存数据结构和文件交换格式，不改变智能体的行为逻辑，确保前后端不因数据格式变更而报错。
*   **后端内存改造**：在 [scratch.py](file:///g:/generative_agents/reverie/backend_server/persona/memory_structures/scratch.py) 的 `__init__` 函数中，初始化代谢属性与技能槽字典：
    ```python
    self.satiety = 100.0   # 饱食度
    self.stamina = 100.0   # 精力值
    self.health = 100.0    # 生命值
    self.inventory = {}    # 背包 {"apple": 0}
    self.skills = {        # 职业技能与熟练度
        "farming": {"level": 1, "xp": 0},
        "cooking": {"level": 1, "xp": 0}
    }
    self.personal_knowledge = {} # 结构化个人知识
    ```
*   **文件对齐**：修改 `reverie.py` 中读写 `storage/` 状态 JSON 文件的逻辑。将新增的生理、背包和技能状态写入 `movement/{step}.json`，使前端可视化面板（如 `/replay_persona_state/`）能够无损读取并展现。

### 2.2 第二步：反应式 ReAct 决策（行为逻辑解耦）
本阶段重构智能体的思维循环，使其从“死板执行计划”过渡到“在环境中灵活求生”。
*   **感知阶段注入生理状态**：修改 [perceive.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/perceive.py)，在 Agent 收集到的感知列表首位插入生理告警（例如：`"I feel very hungry (Satiety: 15/100)"`）。
*   **重构计划循环打断**：
    *   在 [plan.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/plan.py) 的 `decide_next_action` 阶段中，检测 `satiety` 或 `health` 是否低于危险线（例如 20）。
    *   若低于危险线，则在 Scratch 中将 `planned_path` 强制清空，并将当前日常计划标志位挂起。
    *   调用新增的 `generate_survival_plan` 模版，让 GPT 根据当前所处的空间记忆（哪里有食物）生成紧急寻路目标，实现 ReAct 循环。

### 2.3 第三步：技能影响与知识库构建（进化与成长）
本阶段彻底实现智能体的生存进化差异性。
*   **技能影响动作收益**：
    *   修改 [execute.py](file:///g:/generative_agents/reverie/backend_server/persona/cognitive_modules/execute.py) 中的动作判定逻辑。
    *   例如，在执行 `execute_gather` 时，系统查询 `self.skills["farming"]["level"]`。若 Farming 等级高，则随机增算采集到的苹果数量，并为其增算 Farming XP。
    *   XP 累加触发升级后，自动向 Scratch 的 ISS 文本段（在 `get_str_iss` 中）动态附言：`"Isabella is a skilled farmer (Lv.3)."`，使得 LLM 在日后对话中自然流露出专业属性。
*   **文档阅读与知识库写入**：
    *   扩展 `execute.py` 允许读取带有特定 text 内容的家具（书籍/文档）。
    *   读取后将文档包含的配方事实（如 `"apple + water = juice"`）写入 `personal_knowledge["crafting_recipes"]`，实现无痛的知识点扩充。

---

## 3. 性能优化与资源开销控制

由于引入了更频繁的生理检测和 ReAct 循环，需要加强缓存与并行以防本地算力崩溃：

1.  **快速路径条件放宽 (Optimized Fast Path)**：当智能体饱食度安全（> 50）且正处于行走到目的地的路上（`planned_path` 不为空）时，直接跳过 LLM 生存规划计算，仅执行 A* 移动。
2.  **分级模型分配 (Model Routing)**：
    *   使用 `qwen2.5:3b` 来处理简单的“根据生理数值判定是否饥饿”、“计算采集概率”等原子判定任务。
    *   使用 `qwen2.5:7b` 处理复杂的高层“生存策略抉择”、“社交知识共享”和“反思提炼”任务。
3.  **磁盘与内存双缓存 (Dual-Cache)**：对相同 Prompt 采用磁盘缓存，对高频调用的嵌入向量（Embeddings）在 `AssociativeMemory` 运行周期内直接常驻内存字典，规避对 Ollama 的重复 API 访问。
