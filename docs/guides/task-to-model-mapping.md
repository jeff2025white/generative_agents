# 任务与模型路由对应关系表 (Task-to-Model Mapping)

本文档记录了 Generative Agents 系统中各类任务与 LLM 模型及其供应方的映射关系。所有的配置均由 `reverie/backend_server/llm_api_config.py` 统一管理。

## 核心路由配置

目前系统采用 **任务路由 (Task-based Routing)** 架构，通过任务类型自动分流到最合适的模型。

| 任务类型 (Task Type) | 路由配置名 | 实际模型 (Model) | 供应方 (Provider) | 任务描述 |
| :--- | :--- | :--- | :--- | :--- |
| **通用对话** (`general_chat`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 系统基础交互与测试 |
| **社交聊天** (`social_chat`) | `deepseek_chat` | `deepseek-chat` | DeepSeek (云端) | NPC 之间的对话内容生成 |
| **社交决策** (`social_decision`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 决定是否发起或加入社交 |
| **核心决策** (`decision`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | NPC 需求思考与行为决策 (High Value) |
| **计划规划** (`planning`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 每日计划安排与唤醒逻辑 |
| **位置选择** (`location_selection`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 确定动作发生的具体物理坐标 |
| **记忆反思** (`memory_reflection`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 记忆流水提取、总结与重要性评分 |
| **动作翻译** (`translation`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 将 LLM 意图翻译为游戏引擎指令 |
| **事件三元组** (`event_triple`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 提取 (Subject, Predicate, Object) 结构 |
| **安全评分** (`safety_scoring`) | `zhipu_chat` | `glm-4-flash` | 智谱 (云端) | 评估动作的合规性与逻辑自洽性 |

## 当前运行结论

*   **主业务链路默认不上本地聊天模型**: 当前 `TASK_ROUTE_CONFIG_NAMES` 中没有任何任务默认指向 `local`，所以 `general_chat`、`decision`、`planning`、`translation`、`event_triple` 等活跃主链路都走云端。
*   **社交聊天单独走 DeepSeek**: `social_chat` 明确绑定 `deepseek_chat`，用于 NPC 之间的多轮社交对话生成。
*   **本地 Ollama 目前主要负责 Embedding**: 本地仍保留 `LOCAL_LLM_CONFIG`，但从当前活跃路由看，它主要承担向量相关能力与少量兼容回退，不再是默认主聊天模型。

## 调用点到任务路由的映射补充

除了 `llm_api_config.py` 里的任务类型表，以下历史入口也已经显式接入任务路由，避免隐式回落到本地默认聊天配置：

| 具体调用点 | 所在文件 | 显式任务路由 | 说明 |
| :--- | :--- | :--- | :--- |
| `run_gpt_prompt_pronunciatio()` | `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py` | `translation` | 生成表情/拟声输出，归入翻译类轻量任务 |
| `run_gpt_prompt_survival_decision()` | `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py` | `decision` | 生存导向动作选择，属于核心决策 |
| `run_gpt_prompt_demand_decision()` | `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py` | `decision` | 需求导向动作选择，属于核心决策 |
| `ChatSkillPack` 的 `creator` 模式 | `reverie/backend_server/persona/cognitive_modules/skill_packs/chat_skill.py` | `general_chat` | 造物主 / 观察者对 NPC 的问答与指令响应 |
| `ChatSkillPack` 的 `monologue` 模式 | `reverie/backend_server/persona/cognitive_modules/skill_packs/chat_skill.py` | `general_chat` | NPC 自言自语与短独白 |
| `CookSkillPack.cognitive_decision()` | `reverie/backend_server/persona/cognitive_modules/skill_packs/cook_skill.py` | `general_chat` | 烹饪技能里的微型菜谱选择 prompt |

## 本地模型与 Embedding 的关系

| 能力 | 默认执行位置 | 当前状态 |
| :--- | :--- | :--- |
| Chat / Decision / Planning / Translation | 云端 | 当前主链路默认全部显式走任务路由 |
| NPC 社交聊天 (`social_chat`) | 云端 DeepSeek | 当前单独使用 `deepseek-chat` |
| Embedding | 本地 Ollama | 默认使用 `nomic-embed-text` |
| `LOCAL_LLM_CONFIG` (`deepseek-r1:7b`) | 本地 Ollama | 作为兼容配置保留，不是当前主业务默认路由 |

## 可用模型配置池

在 `llm_api_config.py` 中定义了以下配置池，可供路由表引用：

| 配置名 (Config Name) | 供应方 | 模型标识 | 备注 |
| :--- | :--- | :--- | :--- |
| `local` | Ollama (本地) | `deepseek-r1:7b` | 当前主要作为兼容配置保留，可用于离线或定向切回本地 |
| `zhipu_chat` | 智谱 AI (云端) | `glm-4-flash` | **当前系统默认**，平衡了速度与智能 |
| `deepseek_chat` | DeepSeek (云端) | `deepseek-chat` | 当前用于 `social_chat`，适合作为 NPC 对话云端备选 |
| `bailian_chat` | 阿里云百炼 (云端) | `qwen-plus-character` | 角色扮演特化模型备选 |

## 如何修改配置

1.  **全局切换云模型**: 修改 `llm_api_config.py` 中的 `DEFAULT_PRIMARY_CLOUD_CONFIG_NAME` 变量。
2.  **特定任务切换到指定云模型或本地**: 在 `TASK_ROUTE_CONFIG_NAMES` 字典中，将对应任务的值改为 `"deepseek_chat"`、`"zhipu_chat"`、`"bailian_chat"` 或 `"local"`。
    *   例如：将翻译任务改为本地执行：`"translation": "local"`
3.  **切换本地模型**: 修改 `LOCAL_LLM_CONFIG` 中的 `model` 字段（需先通过 `ollama pull` 拉取模型）。
4.  **修改具体历史入口的默认归属**: 若某些旧函数或 skill pack 内部已显式调用 `get_task_route_request_config(...)`，需要同时修改对应代码入口，而不只是改路由表。

## 架构原则

*   **解耦**: 业务代码严禁直接使用模型名称，必须通过 `get_task_route_request_config(task_type)` 获取配置。
*   **成本优化**: 默认使用 `glm-4-flash` 以兼顾免费额度与响应速度。
*   **物理常识兜底**: 决策链路 (`decision`) 生成意图后，由系统规则层进行物理约束检查（如：洗车必须开车去）。
*   **本地优先用于向量，不做隐式聊天默认值**: 本地聊天模型可以保留作为兼容配置，但活跃业务入口应显式声明所属任务路由，避免旧代码在异常路径下悄悄回落到本地聊天模型。
