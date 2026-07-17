# 十动机记忆与经验检索流程

本文说明 NPC 的行动结果如何从运行时状态落盘为记忆，并在下一次决策中按主导、次要动机重新检索和使用。

## 总览

```text
决策生成动作
  → Scratch 保存 action_record（主/次动机、行动前十动机快照）
  → 技能执行
  → 成功 / 失败 / 库存与路径结果
  → 计算十项 motive_effects
  → 保存行动结果、实例经验与关联记忆
  → nodes.json + embeddings.json 落盘

下一次决策
  → 选择主导与次要动机
  → 两路独立召回关联记忆
  → embedding、新近性、重要性初排
  → 动机效果、标签、失败语义重排
  → 主次动机成功/失败经验分组
  → 注入决策 Prompt 与目标约束
```

## 1. 行动开始：记录上下文

`Scratch.set_current_action_record()` 在动作进入计划时保存：

- 技能、目标与解析后的地址；
- 主导动机与次要动机；
- 行动开始前的十项动机值；
- 决策 ID、描述与目标解析元数据。

十项动机是：`satiety`、`stamina`、`health`、`safety`、`mood`、`belonging`、`status`、`autonomy`、`competence`、`meaning`。

## 2. 行动结果：计算动机效果

技能完成或失败时，`build_action_outcome_record()` 读取动作结束后的动机快照，并计算：

- 四项基础状态变化：`satiety`、`stamina`、`health`、`mood`；
- 十项 `motive_effects`；
- 执行状态、失败原因与原因分类；
- 资源类型与 `resource_instance_key`（目标地址的规范化值）。

失败同样是经验：即使没有产生正向动机效果，`resource_empty`、`path_not_found`、`target_not_close` 等失败原因也会被记录。

## 3. 经验与关联记忆落盘

`Scratch.record_action_outcome()` 处理三种持久化信息：

1. 近期行动结果与运行日志。
2. 实例经验：
   - 成功且有足够进展的实例写为 `prefer_this_instance`；
   - 空资源、不可使用等失败实例写为 `avoid_this_instance`；
   - 实例经验带有过期步数，避免将暂时状态永久化。
3. 高价值结果投影为关联记忆节点。

关联记忆节点保存到 `nodes.json`，embedding 保存到 `embeddings.json`。节点包含：

- 传统 `attribute_effects`；
- 十项 `motive_effects`；
- `memory_tags`：主/次动机、技能、目标、地址、状态、失败原因与实例键等。

启动时 `AssociativeMemory` 会恢复这些字段。没有新字段的旧节点保留兼容默认值，并依赖文本、关键词和基础状态效果参与检索。

## 4. 主次动机检索

每次需求决策先由动机选择器确定主导和次要动机，然后执行两路独立检索：

- 主导动机：优先寻找直接改善该动机或与其失败相关的经验；
- 次要动机：独立召回，避免被主导动机候选完全挤掉。

每路检索先以 embedding 相关性、新近性、重要性召回 event 与 thought 记忆；之后按下列证据重排：

- 该记忆对应动机的效果幅度；
- `memory_tags` 中的动机上下文；
- 目标、技能和失败原因的语义匹配；
- 事件的重要性与新近性。

两路候选会按“主导优先、次要补充”去重合并。

## 5. Prompt 中的经验展示

合并后的记忆按相关性分为：

- 主导动机相关；
- 次要动机相关；
- 其他可参考经验。

主导和次要动机各自最多展示两条成功经验、两条失败尝试。失败项使用明确的“避免重复”提示，而不是仅作为背景文本。

实例级经验也以相同方式显示，例如：

```text
主导动机相关（satiety）:
成功实例:
⭐ apple tree worked well recently.
失败实例（避免重复）:
⚠ refrigerator at Dorm kitchen was empty recently.
```

## 6. 防止重复访问空资源

防重复由三层共同承担：

1. 世界资源状态标记该地址库存为空。
2. `failed_resource_instances` 按目标地址保留短期失败记录，并在地址解析时过滤未过期实例。
3. 失败经验被检索并注入 Prompt，提示模型维持同一需要但更换来源。

失败约束以 `target_address` 为粒度：一台空冰箱会被排除，但其他冰箱、苹果树或其他食物来源仍可使用。

## 7. 边界与后续改进

- 关联检索直接读取 event 与 thought；聊天若需要进入该通道，应投影为行动结果 event。
- 旧历史记忆没有十动机效果，只能走兼容性语义检索；新结果记忆具有完整结构化证据。
- 可进一步加入实例经验的置信度衰减、跨地点泛化规则和检索效果遥测，以校准重排权重。
