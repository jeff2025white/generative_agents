# Generative Agents — 决策 Prompt、模型路由与微调训练指南

本文档整合了智能体每步决策（Step Decision）的 Prompt 设计架构、任务路由与模型映射配置、训练数据准备日志契约、架构分层设计备忘，以及调试与反推方法。

---

## 目录
1. [每步决策机制总览](#1-每步决策机制总览)
2. [第一阶段 Prompt：需求思考 (`demand_thinking`)](#2-第一阶段-prompt需求思考-demand_thinking)
3. [第二阶段 Prompt：动作翻译 (`action_translation`)](#3-第二阶段-prompt动作翻译-action_translation)
4. [真实运行决策示例](#4-真实运行决策示例)
5. [动作翻译与程序侧纠偏](#5-动作翻译与程序侧纠偏)
6. [任务路由与模型映射配置](#6-任务路由与模型映射配置)
   - [6.1 架构目标与设计原则](#61-架构目标与设计原则)
   - [6.2 核心配置文件与变量](#62-核心配置文件与变量)
   - [6.3 任务路由与模型映射总表](#63-任务路由与模型映射总表)
   - [6.4 调用点与显式任务路由映射](#64-调用点与显式任务路由映射)
   - [6.5 本地模型与向量嵌入的关系](#65-本地模型与向量嵌入的关系)
   - [6.6 配置修改指南](#66-配置修改指南)
7. [架构分层与本地/云端协同策略](#7-架构分层与本地云端协同策略)
   - [7.1 LLM/World Model/Action Layer 分层方案](#71-llmworld-modelaction-layer-分层方案)
   - [7.2 本地模型与云端 API 协同部署](#72-本地模型与云端-api-协同部署)
8. [微调训练数据准备契约 (Log Contract)](#8-微调训练数据准备契约-log-contract)
   - [8.1 日志路径与字段协议](#81-日志路径与字段协议)
   - [8.2 最小输出约束的三层打断结构](#82-最小输出约束的三层打断结构)
   - [8.3 历史数据回填](#83-历史数据回填)
9. [调试与日志分析](#9-调试与日志分析)
10. [关键代码与模板索引](#10-关键代码与模板索引)

---

## 1. 每步决策机制总览

系统对智能体行为的决策采用**"两阶段认知 + 物理规则收敛"**架构：
1. **第一阶段：认知思考**。大模型充当"大脑"进行主观意图分析，生成自然语言意图。
2. **第二阶段：协议翻译**。将自然语言意图转换为可被物理引擎执行的结构化 JSON。
3. **程序侧纠偏与归一**。对 JSON 输出进行格式校验、食物源可用性纠偏、技能归一，最后由执行层分发至对应的技能包执行。

### 触发重新决策的条件
智能体并非每一步都重新决策（大部分移动状态下走 Fast Path 跳过 LLM）。只有在以下事件发生时才会重新决策：
*   当前正在执行的动作倒计时结束。
*   寻路过程中发生碰撞阻挡，触发导航失败（`navigation_failure`）。
*   生理指标（饱食度或精力）降至危急值（Satiety < 30 或 Stamina < 20），强制清空现有计划，打断当前动作。

---

## 2. 第一阶段 Prompt：需求思考 (`demand_thinking`)

*   **实现函数**：`run_gpt_prompt_demand_thinking()`
*   **模版路径**：`persona/prompt_template/v2/demand_decision_thinking_v1.txt`

### 模板骨架
```text
<identity_summary> (包含名字、性格、职业等 ISS 人设信息)

Temporal Context:
- Current Time: <当前模拟时间>

Previous Activity Context:
- Last Action: <前一动作描述>
Treat the last action only as continuity context. Do not assume the agent is still tired, hurt, or committed to continuing...

Current Status:
- Satiety (0-100): <饱食度>
- Stamina (0-100): <精力值>
- Health (0-100): <生命值>
- Mood (0-100): <情绪值>
- Inventory: <背包物品>

Homeostasis Interpretation:
<status_summary> (由代码生成的各项生理指标文字解释、主观感受和行为建议)

Homeostasis & World Rules:
<rules> (代码注入的世界规律、代谢扣减消耗、切换成本以及危急状态强制硬约束)

Nearby Elements & Resources (including Micro-states):
<nearby_resources> (附近有哪些设施、是否空闲、周边人物的协作期望)

Cooperative Context / Social Expectations:
<cooperative_context> (周围是否有其他角色正在等待我服务，或者正在发起的社交)

Relevant Prior Experience:
<intent_memory_summary> (利用 new_retrieve() 检索并由 LLM 总结的最相关意图记忆)

Decision Convergence Guidance:
<decision_convergence_guidance> (限制发散，要求只做当前最直接的一步决策)

Task: What is the next immediate feasible action for <名字> under the current physical constraints?
Output Requirements:
- 用 <名字> 的第一人称
- 只写一个句子
- 只描述一个即时动作，不要写多步计划
- 只提一个目标物体或地点
- 明确当前最迫切的内部需求
- 优先服务主导动机，不要平均看待所有信息
- 如果主导动机是 mood，应优先说一个直接修复 mood 的即时动作，除非硬性物理约束阻止该选择
- 如果上一个即时动作失败了，或者目标不可达，必须换一个新的即时办法，而不是重复失败目标
- 只有当主导动机对应的首选动作因物理不可行或最新失败反馈而失效时，才允许回退到次优方案
```

---

## 3. 第二阶段 Prompt：动作翻译 (`action_translation`)

*   **实现函数**：`run_gpt_prompt_action_translation()`
*   **模版路径**：`persona/prompt_template/v2/action_translation_v1.txt`
*   **依赖 Schema**：`persona/prompt_template/v2/action_schema.json`

### 模板骨架
```text
You are a precise physical translation engine for a sandbox simulation.

Here is the Action Schema containing the allowed action categories, their allowed target objects, and their descriptions:
<Action Schema 全文>

Here are the interactive targets currently physically near <名字>:
<附近可交互目标列表>

Now, translate <名字>'s natural language intent:
Intent: "<第一阶段输出的自然语言意图>"

Translation Convergence Guidance:
Preserve the immediate intent from the natural language thought. Do not expand into a broader alternative plan...

Respond ONLY in valid JSON format:
{
  "action": "...",  // 必须是 Action Schema 中的标准类别之一 (Consume, Gather, Rest, Work, Socialize, Recreate)
  "target": "...",  // 必须是附近物理上存在的对象名称
  "detail": "...",  // 给人读的动作详细文字描述
  "duration": ...,  // 预估动作时长(分钟)
  "reasoning": "..." // 物理映射解释
}
```

---

## 4. 真实运行决策示例

以下是以研究生 Klaus Mueller 处于饥饿危机下为例的真实决策上下文与模型输出：

### 4.1 第一阶段思考
*   **输入 status_summary (Satiety = 24.0)**：`"severely hungry. Getting food should outweigh leisure, work, or rest. Ignoring food now risks health deduction."`
*   **输入 rules (Inventory = empty)**：`"CRITICAL HOMEOPATHY RULE: Satiety is critically low! Since your inventory is empty, you CANNOT select 'Consume'. You MUST select 'Gather' targeting 'refrigerator', 'stove', 'cafe counter', or 'apple tree' to get food first!"`
*   **LLM 意图输出**：`"I am severely hungry and my inventory is empty, so I want to gather food from the cafe counter right now."`

### 4.2 第二阶段翻译
*   **输入 Intent**：`"I am severely hungry and my inventory is empty, so I want to gather food from the cafe counter right now."`
*   **输入 nearby_resources**：`"refrigerator, cafe counter, apple tree, sofa, bed"`
*   **LLM 翻译输出**：
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

## 5. 动作翻译与程序侧纠偏

即使大模型输出成功，代码在保存前还会做一轮防崩溃纠偏：
*   **动作改写**：当 LLM 输出 `action="Consume"` 但背包（inventory）无对应食物时，程序自动将其修正为 `Gather`。
*   **非法目标重定向**：当 LLM 输出的 `target` 并非合法食物源时，程序自动将其回退到最近的可用对象。
*   **映射 `skill_id`**：根据 `action` 字段归一化为执行层可以路由的技能标识（如 `gather`、`consume`、`rest`）。
*   **匹配物理地址**：在空间树中寻找该 `target` 的物理路径写入 `act_address`。

---

## 6. 任务路由与模型映射配置

### 6.1 架构目标与设计原则

项目目前采用"任务类型 → 配置名 → 实际模型"的中心化路由架构，旨在达成以下设计原则：
*   **解耦模型供应商**：业务代码严禁直接使用特定模型名称（如 `gpt-4` 或 `qwen-plus`），必须通过 `get_task_route_request_config(task_type)` 获取配置。切换云模型或供应商时只需修改配置中心，无需改动任何业务逻辑。
*   **精细化分工（Cost & Performance Optimization）**：不同等级的任务可拆分到不同参数的模型版本。例如，高价值的决策和规划任务路由到更聪明的模型，简单的翻译、表情提取路由到低成本/高吞吐的模型。
*   **物理常识兜底**：大模型生成动作意图后，必须由底座的规则或物理拦截器进行可行性校验，防止大模型产生物理上无法实现的意图。

### 6.2 核心配置文件与变量

所有的任务路由及 API 密钥配置均集中在以下文件中管理：
*   **主配置文件**：[llm_api_config.py](file:///Users/gun/mygame/generative_agents/reverie/backend_server/llm_api_config.py)

#### 核心配置结构
1.  **`_REQUEST_CONFIGS`**：维护"配置名 → `api_key`/`api_base`/`model`"的底层原始映射，包括云端和本地服务信息。
2.  **`DEFAULT_PRIMARY_CLOUD_CONFIG_NAME`**：全局默认云模型的总开关。当某类任务没有配置专属路由时，默认回退到该配置指向的云模型。
3.  **`TASK_ROUTE_CONFIG_NAMES`**：任务中心路由表，定义每个任务类型应该使用的配置名。
4.  **`get_task_route_request_config(task_type)`**：供业务模块调用的核心入口，按任务类型动态获取最终请求配置字典。

### 6.3 任务路由与模型映射总表

目前系统支持的配置池（可用模型）包括：
*   `local`：本地 Ollama 运行的 `deepseek-r1:7b`；
*   `zhipu_chat`：智谱云端的 `glm-4-flash`（**系统主默认云模型**）；
*   `deepseek_chat`：DeepSeek 云端的 `deepseek-chat`；
*   `bailian_chat`：阿里云百炼云端的 `qwen-plus-character`。

以下是当前系统各个任务类型的路由映射明细：

| 任务类型 (Task Type) | 路由配置名 | 实际模型 (Model) | 供应方 (Provider) | 任务描述 |
| :--- | :--- | :--- | :--- | :--- |
| **通用对话** (`general_chat`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 包含造物主沟通、NPC 独白、测试对话 |
| **社交聊天** (`social_chat`) | `deepseek_chat` | `deepseek-chat` | DeepSeek (云端) | NPC 之间多轮社交对话正文及台词生成 |
| **社交决策** (`social_decision`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 决定是否发起社交或接受聊天 |
| **核心决策** (`decision`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 需求评估、生理危机的 ReAct 求生决策 |
| **计划规划** (`planning`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 每日初始规划、唤醒时间和行动日程分解 |
| **位置选择** (`location_selection`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 寻找动作发生的具体家具、房间或坐标 |
| **记忆反思** (`memory_reflection`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 记忆流水反思、提取 Insights 与重要性评分 |
| **动作翻译** (`translation`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 将 LLM 意图翻译为物理动作 Schema |
| **事件三元组** (`event_triple`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 提取 (Subject, Predicate, Object) 事件 |
| **安全评分** (`safety_scoring`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 评估动作的合规性与逻辑自洽 |

### 6.4 调用点与显式任务路由映射

为防止隐式回退到本地默认聊天配置，系统在所有关键的大模型 Prompt 发生处均显式传入了任务类型：

| 具体调用点 | 所在文件 | 显式任务路由 | 说明 |
| :--- | :--- | :--- | :--- |
| `run_gpt_prompt_pronunciatio()` | `run_gpt_prompt.py` | `translation` | 生成动作对应的表情或拟声输出 |
| `run_gpt_prompt_survival_decision()` | `run_gpt_prompt.py` | `decision` | 生存导向下的核心求生动作决策 |
| `run_gpt_prompt_demand_decision()` | `run_gpt_prompt.py` | `decision` | 日常需求驱动下的核心日常动作决策 |
| `ChatSkillPack` 的 `creator` 模式 | `chat_skill.py` | `general_chat` | 响应造物主的问答与强制物理指令 |
| `ChatSkillPack` 的 `monologue` 模式 | `chat_skill.py` | `general_chat` | 智能体自言自语与短独白 |
| `CookSkillPack.cognitive_decision()` | `cook_skill.py` | `general_chat` | 烹饪技能中的食谱微选择决策 |

### 6.5 本地模型与向量嵌入的关系

*   **业务决策链路默认不上本地聊天模型**：当前 `TASK_ROUTE_CONFIG_NAMES` 中没有任何任务默认指向 `local`。`general_chat`、`decision`、`planning` 等主业务链路都在云端运行。
*   **本地 Ollama 主要负责向量计算 (Embedding)**：本地依然维持了 Ollama 的调用配置，默认使用模型 **`nomic-embed-text`** 进行记忆流节点的向量嵌入计算与余弦相似度召回。
*   **本地 DeepSeek 保留兼容**：本地 `deepseek-r1:7b`（`local`）可作为云端网络故障或离线断网情况下的低成本后备路由。

### 6.6 配置修改指南

#### 全局切换默认云模型
如果您希望将所有默认回退的任务统一切换到 DeepSeek 或阿里百炼，只需修改 `llm_api_config.py` 中的 `DEFAULT_PRIMARY_CLOUD_CONFIG_NAME` 变量：
```python
# 将全局默认云模型由智谱切换至 DeepSeek
DEFAULT_PRIMARY_CLOUD_CONFIG_NAME = "deepseek_chat"
```

#### 将特定任务路由到指定模型
如果只想单独调整某类任务的模型，可以直接在 `TASK_ROUTE_CONFIG_NAMES` 字典中重设其映射值：
```python
TASK_ROUTE_CONFIG_NAMES = {
    ...
    "planning": "deepseek_chat",
    "translation": "local",  # 本地 Ollama 运行
    ...
}
```

#### 切换本地 Ollama 模型
若想在本地使用其他大语言模型，必须首先在终端运行 `ollama pull <model_name>`，然后修改 `llm_api_config.py` 中 `local` 配置的 `model` 字段：
```python
_REQUEST_CONFIGS = {
    "local": {
        "api_key": "ollama",
        "api_base": "http://localhost:11434/v1",
        "model": "qwen2.5:7b"  # 修改为新拉取的本地模型
    },
    ...
}
```

---

## 7. 架构分层与本地/云端协同策略

> 本节整理自 2026 年 7 月 3 日关于系统决策不稳、模型微调方向的内部讨论备忘。

### 7.1 LLM/World Model/Action Layer 分层方案

随着在生存、健康、寻路等高频决策链路上进行测试，系统暴露出了明显的瓶颈：LLM 擅长理解上下文和生成人设台词，但在理解硬性物理约束、防止格式出错和失败后重规划方面表现极不稳定。

我们主张**不应机械照搬"VLA"或端到端具身智能术语**，而是针对文本规则沙盒进行适配：
*   **LLM (大脑)**：负责主观理解与策略候选生成。例如："我现在饿了，要优先补充食物"。
*   **World Model (预测层)**：负责可行性与后果预测。预测候选动作是否可行、到达目标是否有路径、预计状态收益与损失。
*   **Action Layer (执行层)**：负责动作约束校验、结构化映射与物理执行闭环。

#### 建议的五层工程架构
```
State Compiler (状态编译) -> LLM Policy (意图策略) -> World Model (可行性预测) 
  -> Action Resolver/Executor (动作解析与执行) -> Post-Execution Critic (执行后评判)
```

1.  **State Compiler (状态编译)**：将 scratch、记忆、物品、时间编译为统一格式，降低 Prompt 的冗余叙事噪声。
2.  **LLM Policy (意图策略)**：只输出高层策略（如"去冰箱拿吃的"、"休息"、"找人说话"），不直接输出可执行底层地址。
3.  **World Model (预测层)**：评估候选意图可行性，预测代价并做失败经验命中校验。
4.  **Action Resolver/Executor (动作执行层)**：将意图映射到具体 Object，输出 Action Schema，做物理执行。
5.  **Post-Execution Critic (执行后评判)**：记录失败原因，参与下一轮候选空间过滤，防止叙事惯性引起立刻回跳重试。

#### 社交聊天 vs 生存决策链路差异
*   **社交聊天链路**：属于高自由度、随机性任务。适合继续以 **LLM 为绝对主导**。保留对格式和记忆污染的校验即可。
*   **生存、生理、移动链路**：属于高风险、强约束任务。适合采用 **高约束决策架构**。必须经过 World Model 的可行性过滤和 Action Layer 的物理守卫。

#### 折中策略
前期无需直接堆砌神经网络版 World Model 或具身智能级别的 VLA，而是通过 **结构化命令协议 (`act_command`)**、**物理空间匹配器 (`action_target_resolver`)** 以及 **技能包契约 (`BaseSkillPack`)** 构建一个轻量、规则导向的物理底座。这既能保障大脑（LLM）继续进行社会性角色涌现，又通过 Action Layer 限制了物理行为的失控。

### 7.2 本地模型与云端 API 协同部署

不建议在项目中采取"非此即彼"的纯自研或纯云端策略，而是根据任务类型进行协同分工。

#### 本地部署的真实拥有成本
本地部署包含多重隐性成本：GPU 显存占用上限、电费与维护成本、框架版本运维时间，以及为了处理不同任务而在显存中频繁载入不同模型带来的拥堵时延。
*   如果系统调用高频、文本短、规则限制多，则本地算力优势大。
*   如果调用不频繁、对质量敏感且需要不断变更模型验证表现，线上 API 更便宜、更灵活。

#### 任务分流与协同路由原则
*   **本地模型常驻层**：负责高频、短文本、时延敏感、可约束的基础逻辑（如生理状态初筛、表情拟声提取、向量嵌入计算）。
*   **云端 API 增强层**：负责高质量生成、大上下文理解、多轮复杂社交会话。
*   **协同路由层**：业务代码调用统一的 `get_task_route_request_config(task_type)`。通过该收口管理路由规则，必要时可快速一键将某类任务切到本地或指定云端模型。

---

## 8. 微调训练数据准备契约 (Log Contract)

为了向定向模型微调提供高质量、可观测的训练样本，系统在决策生命周期内引入了**最小决策过滤与数据准备契约**。

### 8.1 日志路径与字段协议

**日志路径**：`logs/training_dataset/decision_training_prep.jsonl`

每行必须是一个合法的 JSON 对象，包含以下核心字段：

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `decision_id` | `string` | 唯一标识符，可用于 join 关联同一决策下的其他事件 |
| `persona` | `string` | 智能体名称 |
| `curr_step` | `int` | 当前仿真 Step |
| `event` | `string` | 决策阶段（如 `demand_thinking` 或 `action_translation`） |
| `ts` | `string` | 标准 ISO-8601 时间戳 |
| `prompt_kind` | `string` | Prompt 分类（如 `demand_decision_v1`） |
| `final_prompt` | `string` | 组装填充后的完整 Prompt 文本 |
| `prompt_hash` | `string` | 完整 Prompt 的 MD5 摘要，用于快速对比去重 |
| `decision` | `object` | LLM 或程序纠偏后的结构化决策输出 |
| `constraint_hit` | `bool` | 是否命中了程序侧强制干预或纠偏规则 |
| `retry_reason` | `string` | 若发生了格式解析错误触发重试，记录重试原因 |
| `execution_outcome` | `string` | 本次动作的最终执行结果（`success`, `path_not_found`, `skill_blocked`） |
| `minimal_filter_enabled` | `bool` | 是否启用了最小化过滤 |
| `minimal_filter_applied` | `bool` | 本次决策是否实际命中了排除条件 |
| `minimal_filter_summary` | `string` | 过滤的简短依据归因 |
| `schema_version` | `string` | 日志契约的版本号 |

**格式化规则**：
*   每行必须是一条独立的记录，不能包含非法的换行符或 Markdown 代码块包裹。
*   复杂字段（如 `decision`）必须保留为结构化 JSON 对象（Map），不得强制压缩为纯文本字符串。

### 8.2 最小输出约束的三层打断结构

> 痛点：在测试中，Isabella Rodriguez 在前往 `apple tree` 失败且拿到了明确失败记录后，LLM 仍然会在下一步以极高的概率继续输出 `apple tree` 作为下一目标。仅仅通过 Prompt 润色"请换个目标"已达到瓶颈，必须从硬性拦截和数据沉淀入手。

为了不夺走 LLM 的自主决策权，只阻止它犯下明显错误，我们设计了以下三层打断结构：
1.  **第一层：`InvalidTargets` 列表**：在当前 Step 拼装第一阶段 Prompt 时，代码把本轮已确认失效的目标列为 `InvalidTargets`（这并非建议，而是本轮强行禁选目标）。
2.  **第二层：`Resources` 动态过滤**：在构建 Nearby Elements 资源列表时，代码自动剔除最近失败的对象，减少 LLM 在上下文中看到的概率。
3.  **第三层：输出后校验拦截**：在第二阶段 LLM 输出 JSON 后，做一次底层极小校验。如果目标依然命中 `InvalidTargets` 且背包为空，直接由程序侧强行重定向至冰箱等其他有效食物源（或触发单次重试），并写入日志记录 constraint hit。

#### 四阶段优先级路径
1.  **第一步（止血）**：引入"最小输出约束"层，用规则强制打断 LLM 重复失败目标。
2.  **第二步（可观测）**：改造日志，为每次决策生成 `decision_id`，保存 `final_prompt`，建立统一的微调训练准备日志。
3.  **第三步（候选池）**：筛选积累"LLM 决策出错被物理纠偏"的高价值负样本。
4.  **第四步（微调）**：等样本数量充足、标注完整后，再开辟定向的微调训练链路。

### 8.3 历史数据回填

若历史日志中缺失 `decision_id` 等核心契约字段，可使用系统内置的回填工具：
*   **回填脚本**：`test/check_backfill_training_prep_logs.py`
*   **Dry-run 测试模式**：不修改文件，只输出需要回填和调整的行数及原因。
*   **原地写入模式**：运行命令携带 `--write` 参数。脚本会首先在同目录下创建带时间戳的备份文件，然后安全地原地重写 JSONL 日志。

---

## 9. 调试与日志分析

### 9.1 智能体运行日志对照 (`logs/agents/<sim_code>/<persona_name>.jsonl`)
在开启 `ENABLE_AGENT_PROMPT_LOGS` 后，系统会自动转储智能体经历的每一次 Prompt 详细信息，其核心是一个名为 `prompt_input` 的元组数组。以 `demand_decision_thinking_v1.txt` 模板为例，其在 JSONL 中的数组元素与 Prompt 占位符一一对应：

```text
prompt_input[0]  -> identity_summary (ISS 静态设定)
prompt_input[1]  -> satiety (饱食度数值)
prompt_input[2]  -> stamina (精力值数值)
prompt_input[3]  -> health (生命值数值)
prompt_input[4]  -> mood (情绪值数值)
prompt_input[5]  -> inventory (背包物品)
prompt_input[6]  -> nearby_resources (附近设施与微状态)
prompt_input[7]  -> temporal_context (当前虚拟时间)
prompt_input[8]  -> status_summary (文字生理状态解释)
prompt_input[9]  -> rules (代谢与强约束世界规则)
prompt_input[10] -> cooperative_context (社交协作期望)
prompt_input[11] -> firstname (人名)
prompt_input[12] -> last_action_desc (上一次动作)
prompt_input[13] -> intent_memory_summary (记忆召回摘要)
prompt_input[14] -> decision_convergence_guidance (收敛提示)
```

### 9.2 快速排查步骤
1.  **确认决策大方向**：看日志中 `prompt_input[8] (status_summary)`，若生理值见底但状态解释没有表达出紧迫性，说明生理敏感度计算出错。
2.  **检查资源可见性**：看 `prompt_input[6] (nearby_resources)` 中是否由于空间匹配错误导致冰箱或树木丢失。
3.  **诊断执行失败**：如果在执行日志中看到 `skill_blocked`，而微调日志显示大模型输出了正常的动作，说明大模型成功决定，但物理前置条件（如背包原材料数量）被底层引擎拦截。

---

## 10. 关键代码与模板索引

*   **决策调度与翻译纠偏**：[plan.py](file:///Users/gun/mygame/generative_agents/reverie/backend_server/persona/cognitive_modules/plan.py)
*   **Prompt 组装入口**：[run_gpt_prompt.py](file:///Users/gun/mygame/generative_agents/reverie/backend_server/persona/prompt_template/run_gpt_prompt.py)
*   **日志写入机制**：[print_prompt.py](file:///Users/gun/mygame/generative_agents/reverie/backend_server/persona/prompt_template/print_prompt.py)
*   **LLM 路由配置**：[llm_api_config.py](file:///Users/gun/mygame/generative_agents/reverie/backend_server/llm_api_config.py)
*   **需求思考模板**：`reverie/backend_server/persona/prompt_template/v2/demand_decision_thinking_v1.txt`
*   **动作翻译模板**：`reverie/backend_server/persona/prompt_template/v2/action_translation_v1.txt`
