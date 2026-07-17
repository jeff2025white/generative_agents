# 数据持久化与决策画像刷新设计指南

本文档系统介绍了 NPC 的数据持久化方案（运行时事实层 `ActionOutcomeRecord`）以及阶段 1 提示词画像与上下文生成系统的刷新机制。

---

## 1. 运行时事实层：ActionOutcomeRecord 与持久化

为了建立一套统一的**执行结果事实层**，技能执行层和记忆/决策层之间通过结构化的 `ActionOutcomeRecord` 进行数据对接与持久化。

### 1.1 设计目标
*   **统一事实来源**：技能成功、失败、前置条件不满足、资源为空等结果，统一产出结构化结果，不再由不同层各自拼装提示文本。
*   **支持三层消费**：决策首层（Stage 1）判断接下来想做什么；翻译层（Stage 2）约束翻译的动作/目标；解析层避免对同一资源实例重复重试。
*   **物理事实与记忆投影分离**：`ActionOutcomeRecord` 是执行物理事实；`ActionExperienceMemory` 是记忆系统消费的语义投影，两者进行解耦。

### 1.2 核心数据结构
每次技能执行结束时，会生成一条 `ActionOutcomeRecord` 并追加写入 `logs/action_outcome.jsonl` 中。核心字段结构如下：

```json
{
  "schema_version": 2,
  "outcome_id": "uuid-or-step-skill-hash",
  "sim_code": "sim_20260716_233910",
  "persona": "Isabella Rodriguez",
  "curr_step": 161,
  "sim_time": "2026-07-16 23:45:10",
  "wall_ts": "2026-07-17T09:12:00.509613+08:00",
  "decision_capsule": {
    "decision_id": "Isabella_Rodriguez-161-ab12cd34",
    "dominant_motive": "satiety",
    "secondary_motive": "mood",
    "thought": "I should gather food from the apple tree."
  },
  "action": {
    "skill_id": "gather",
    "target": "apple tree",
    "detail": "gathering apples from the apple tree"
  },
  "execution": {
    "status": "success",
    "target_address": "the Ville:garden:apple tree",
    "elapsed_steps": 12,
    "failure_reason": null
  },
  "effects": {
    "self": {
      "stamina_change": -0.84,
      "satiety_change": 0.0,
      "inventory_delta": {"apple": 1}
    },
    "motive_feedback": {
      "satiety_motive_gain": 0.0
    }
  }
}
```

*   **sim_code 补全保障**：在实跑中，若 Scratch 在结算动作时构造了临时 Persona 上下文，可能导致 `sim_code` 变为 `null`。系统优化了 `sim_code` 恢复的提取顺序：
    1. 优先采用当前传入的 `persona.sim_code`；
    2. 若为空，回退使用 `scratch._persona_ref.sim_code`；
    3. 若仍为空，使用 `scratch.sim_code`。

### 1.3 运行时短期聚合（Scratch Views）
最近几次技能的 outcome 记录（尤其是失败记录）会被保存在智能体 [scratch.py](file:///Users/gun/mygame/generative_agents/reverie/backend_server/persona/memory_structures/scratch.py) 的运行时变量中：
*   `scratch.last_action_desc`：上一次动作的文本描述（含失败原因后缀）。
*   `scratch.invalid_targets`：最近因条件不满足或寻路失败被标记为禁用的 `(target, skill_id)` 组合。在下一步决策时，决策管线会读取并强制规避这些无效目标。

---

## 2. 阶段1提示词画像与上下文刷新设计

阶段 1 决策提示词（`demand_thinking`）负责让 LLM 在当前物理约束与主导动机下，输出一句第一人称想法：
`“这个 NPC 在当前约束下，下一步最可行的即时动作想做什么？”`

为保证提示词的稳定性和高可读性，系统将提示词输入拆分为**持久画像层**和**即时编译层**：

### 2.1 整体分层机制
*   **云模型预总结层（Cloud Pre-Summarization - 异步/低频）**：对中长期的静态/半静态字段进行处理并缓存，避免每个 step 重复调用大模型总结导致的超高延迟与费用。
*   **本地即时编译层（Local Runtime Compilation - 每步即时）**：读取最新生理数值、物理规则、无效目标及记忆检索结果，快速拼装出高实时的上下文。

```text
NPC 结构化状态 / 心理动机 / 技能 / 关系 / 原始记忆
  -> Cloud Pre-Summarizer (低频 / 日级刷新)
  -> 写入并持久缓存为 NPC 画像字段
  
当前时刻 / 生理状态口语化 / 附近可达资源 / 失败反馈 / 记忆检索
  -> Local Runtime Compiler (每步实时编译)
  -> 组合成 Stage 1 Prompt
  -> LLM 生成 Thought
```

### 2.2 阶段 1 提示词画像核心字段
画像字段作为中长期复用信息，直接挂载在 NPC 的结构化变量中（如 `scratch.json`），其刷新频率与来源如下：

| 画像字段 | 字段作用说明 | 刷新来源 | 刷新频率 |
| :--- | :--- | :--- | :--- |
| **天生特质 (Innate Traits)** | 刻画 NPC 骨子里的性格与人设（如 "Maria is an outgoing cafe owner..."） | Innate Traits 静态文件 | 初始配置后不刷新 |
| **后天特质 (Learned Traits)** | 从长期经历中抽象出的习惯与反射（如 "Prefers cooking at home when low on money..."） | 长期记忆 $\rightarrow$ 云模型总结 | 日级或大节点手动触发 |
| **当前情景 (Situation)** | 当前所处的重要生活状态（如 "Preparing for the weekend cafe promotion..."） | 近期记忆集 $\rightarrow$ 云模型总结 | 每隔若干模拟步或手动刷新 |
| **生活方式 (Lifestyle)** | 惯常的时间安排偏好（如 "Usually sleeps late and eats near noon..."） | 长期日程历史 $\rightarrow$ 云模型总结 | 日级或定期刷新 |
| **今日计划 (Daily Plan)** | 当天醒来时规划的粗粒度日程表 | Traits + 长期目标 $\rightarrow$ LLM 一日规划 | 每日清晨醒来时刷新一次 |
| **长期目标 (Long-term Goals)** | 智能体的核心长期追求，是社交与高级任务的驱动源，但其优先级不可压过即时生存 | 身份基础人设 $\rightarrow$ LLM 修正 | 初始生成，大阶段更新 |

### 2.3 物理规则与即时反馈的本地编译
以下字段属于**绝对禁止云总结**的即时状态，在每步决策触发时通过本地代码强制拼装：
1.  **生理状态口语化表达**：将饱腹度、精力等数值转换为智能体容易代入的主观感受。例如精力 25.0 时不直接传入 25，而是转译为：`Interpretation: exhausted. Feeling: Your body feels extremely heavy and drained.`
2.  **物理红线规则注入**：若饱腹度/精力低于 30.0 警戒线，在 Prompt 头部强制置顶注入生存限制法则（如 *“Satiety is critically low! Since your inventory is empty, you MUST select 'Gather' targeting refrigerator/stove to acquire food.”*）。
3.  **失败反馈 (Invalid Targets) 与 DecisionGuidance 纠错注入**：将运行时失效的目标、最近失败原因以及物理约束校验失败反馈（如 `inventory_missing`、`self_target_forbidden`）以 `DecisionGuidance: <VALIDATION_FEEDBACK>` 形式显式注入到决策胶囊中，促使模型改变输出并使 Prompt 产生新的 Hash，防止重复相同的物理无效动作。
4.  **策略契约校验约束**：非危急生理危机（严重饥饿、疲劳等）下，决策校验层会强制校验并确保 `strategic_intent`（动作服务的长远目标）和 `expected_followup`（完成后动作）非空，且 `risk`（可能导致失败的风险）在任何情况下都必须非空。
5.  **结构校验与错误信息丰富化**：结构校验器 `gpt_structure.py` 现在不仅返回是否通过，还能输出具体的 `validation_errors` 列表，在安全重试日志中记录原始响应、解析结果和错误列表，极大提升了对 JSON 解析失败、自指目标或缺失字段的可观测性。
6.  **收敛提示与输出限制**：注入严格的单句 thought 第一人称输出契约，限制单次模型生成的 token 数量，防止格式发散与废话。

