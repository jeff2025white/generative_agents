# Chat Storage Contract

## 目标

聊天相关信息最终只保留在两处持久化位置：

1. `logs/chat_transcript.jsonl`
2. `environment/frontend_server/storage/.../personas/<name>/bootstrap_memory/associative_memory/nodes.json`

## 唯一原文入口

`logs/chat_transcript.jsonl`

- 用途：保存聊天逐句原文。
- 覆盖范围：
  - NPC 与 NPC 的社交对话
  - Creator / 用户 与 NPC 的问答
- 关键字段：
  - `dialogue_id`
  - `persona`
  - `target`
  - `sim_time`
  - `step`
  - `channel`
  - `turn_count`
  - `conversation`

## 唯一长期沉淀入口

`associative_memory/nodes.json`

- 用途：保存聊天相关的长期记忆沉淀。
- 主要形态：
  - `type = "chat"`：保存会话节点，`filling` 中包含逐句对话。
  - `type = "event"` / `type = "thought"`：保存对话摘要、反思、八卦、关系变化等高层语义结果。

## 不再作为聊天持久化入口的位置

以下位置仍可能保留运行态或流程态数据，但不再承担“聊天信息持久化”的职责：

- `scratch.json`
  - 不再落盘 `chat`、`chatting_with`、`last_chat`、`chatting_with_buffer`、`chatting_end_time`、`social_dialogue_*`
- `logs/social_dialogue_debug.jsonl`
  - 仅保留社交流程诊断事件
  - 不再保存聊天原文、摘要正文、八卦正文、反思正文

## 查询建议

- 查原文：先看 `logs/chat_transcript.jsonl`
- 查长期记忆沉淀：看对应角色的 `associative_memory/nodes.json`
- 查流程问题：看 `logs/social_dialogue_debug.jsonl`
