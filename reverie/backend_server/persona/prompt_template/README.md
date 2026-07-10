# Prompt Template Directory

本目录存放 NPC 认知、规划、记忆、社交与动作翻译相关的 prompt 模板，以及对应的拼装与调用代码。

## 目录结构

- [run_gpt_prompt.py](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/prompt_template/run_gpt_prompt.py)
  Prompt 调用入口。负责选择模板、组装输入、路由模型请求。

- [gpt_structure.py](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/prompt_template/gpt_structure.py)
  Prompt 结构拼装与输入替换相关逻辑。

- [print_prompt.py](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/prompt_template/print_prompt.py)
  Prompt 调试和打印辅助。

- [v1](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/prompt_template/v1)
  早期模板层。当前仍有少量位置选择/对象选择链路在使用。

- [v2](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/prompt_template/v2)
  当前主线模板层。阶段 1 `demand_thinking`、阶段 2 `action_translation`、`joint_decision` 等核心链路主要在这里。

- [v3_ChatGPT](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/prompt_template/v3_ChatGPT)
  一套保留下来的 ChatGPT 风格模板。当前仍有部分辅助链路和记忆反思相关任务在使用，但不是主决策链的核心模板层。

- [dialogue](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/prompt_template/dialogue)
  对话系统专用模板。
  包含：
  - `generation/`：生成对话内容
  - `initiation/`：决定是否发起对话
  - `reflection/`：对话后的总结、关系提炼、poignancy 评分

- [safety](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/prompt_template/safety)
  安全或约束相关模板。

## 当前维护建议

- 新的主决策模板，优先放在 `v2/`。
- `v1/` 和 `v3_ChatGPT/` 不是完全废弃，但更像历史兼容层和辅助任务层。
- 如果要清理旧模板，先检查 [run_gpt_prompt.py](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/prompt_template/run_gpt_prompt.py) 中是否仍有实际引用。

## 你现在最可能会改到的文件

- 阶段 1 决策模板：
  [v2/demand_decision_thinking_v1.txt](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/prompt_template/v2/demand_decision_thinking_v1.txt)

- 阶段 2 动作翻译模板：
  [v2/action_translation_v1.txt](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/prompt_template/v2/action_translation_v1.txt)

- 阶段 2 结构化动作 schema：
  [v2/action_schema.json](/Users/gun/mygame/generative_agents/reverie/backend_server/persona/prompt_template/v2/action_schema.json)
