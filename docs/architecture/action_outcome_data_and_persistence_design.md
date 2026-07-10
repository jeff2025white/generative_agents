# Generative Agents — 技能执行结果数据结构与落盘方案设计

本文档定义 NPC 在 **每次技能执行结束** 后应产出的统一结构化结果（`ActionOutcomeRecord`），以及该结果如何：

1. 落盘为可回放、可调试、可训练的数据日志；
2. 投影为长期/短期经验，供记忆系统检索；
3. 传递给 Stage1、Stage2 和目标解析层，支持下一步决策与实例级重规划；
4. 基于“对自己/他人的动机或属性影响 + 时效”筛选是否晋升为“经验”。

本设计的目标不是替代现有 `AssociativeMemory`，而是在技能执行层和记忆/决策层之间建立一套统一的 **执行结果事实层**。

---

## 1. 设计目标

本设计希望解决以下问题：

1. **统一事实来源**：技能成功、失败、前置条件不满足、资源为空等结果，不再由不同层各自拼装提示文本，而是统一产出结构化结果。
2. **支持三层消费**：
   - `Stage1` 用执行结果判断“接下来想做什么”；
   - `Stage2` 用执行结果约束“应该翻译成什么动作/目标”；
   - `解析层` 用执行结果避免“同一资源实例”重复重试。
3. **支持记忆晋升**：不是所有执行结果都值得进入长期记忆，需要一套“重要程度 + 时效”的筛选机制。
4. **支持经验学习**：成功经验应帮助系统偏向可行路径，失败经验应帮助系统规避无效路径。
5. **支持实例级资源经验**：系统需要区分“冰箱”这个类别，与“`the Ville:Hobbs Cafe:cafe:refrigerator`”这个具体资源实例。

---

## 2. 总体分层

建议将技能执行结果分为四层：

1. **原始事实层（ActionOutcomeRecord）**
   - 每次技能执行结束时生成一条结构化记录。
   - 是系统内唯一的事实源（source of truth）。

2. **运行时聚合层（Scratch Runtime Views）**
   - 将最近若干条 outcome 投影到 `scratch` 的短期结构中。
   - 供 Stage1、Stage2、解析层快速读取。

3. **记忆投影层（ActionExperienceMemory）**
   - 将值得记住的 outcome 转换为适合 `AssociativeMemory` 存储和检索的经验记忆节点。

4. **追加型日志层（JSONL Persistence）**
   - 全量持久化，便于回放、分析、训练和 debug。

总体流程如下：

```text
Skill 执行结束
  -> 生成 ActionOutcomeRecord
  -> 写入 action_outcome.jsonl
  -> 更新 scratch 运行时视图
  -> 计算 experience_scoring
  -> 若达到阈值，投影为 ActionExperienceMemory
  -> 写入 AssociativeMemory
```

---

## 3. 核心设计原则

### 3.1 一次执行，只生成一条标准 outcome

不允许多个层各自维护“技能是否成功”“失败原因是什么”“刚才去了哪个地址”等重复事实。

### 3.2 原始事实和记忆投影分离

`ActionOutcomeRecord` 是执行事实；`ActionExperienceMemory` 是记忆系统消费的语义投影。两者不能混为一谈。

### 3.3 自己与他人的影响分离

执行结果既可能影响自己，也可能影响他人。必须同时支持：

- 对自己的属性/动机影响；
- 对他人的属性/动机影响；
- 对关系的影响。

### 3.4 类别级目标与实例级目标分离

必须同时保留：

- `target = refrigerator`
- `target_address = the Ville:Hobbs Cafe:cafe:refrigerator`

否则无法支持“同类资源可切换、同一实例不可重试”的约束。

### 3.5 经验写入必须经过筛选

不是所有执行结果都值得进入长期记忆。应结合：

- 结果重要程度；
- 动机/属性变化；
- 对他人的影响；
- 失败学习价值；
- 时效衰减；

计算是否晋升为长期经验。

---

## 4. 原始事实层：ActionOutcomeRecord

`ActionOutcomeRecord` 是每次技能执行结束后产出的标准结构。

建议字段如下。

### 4.1 顶层结构

```json
{
  "schema_version": 1,
  "outcome_id": "uuid-or-step-skill-hash",
  "sim_code": "sim_20260710_113627",
  "persona": "Isabella Rodriguez",
  "curr_step": 161,
  "sim_time": "2026-07-10 08:12:20",
  "wall_ts": "2026-07-10T11:38:01.509613+08:00",
  "decision_context": {},
  "action": {},
  "execution": {},
  "effects": {},
  "resource_context": {},
  "experience_scoring": {},
  "memory_projection": {}
}
```

---

## 5. 字段分组设计

### 5.1 `decision_context`

记录这次执行背后的决策上下文，供 Stage1/Stage2/分析工具使用。

```json
"decision_context": {
  "decision_id": "Isabella_Rodriguez-161-ab12cd34",
  "pipeline": "thinking_translation",
  "thought": "I should try to find food right now.",
  "dominant_motive": "satiety",
  "secondary_motive": "mood",
  "dominant_urgency_band": "warning",
  "dominant_strength": "strong",
  "has_urgent_motive": true
}
```

#### 用途

- 帮助 Stage1 理解“这次动作原本是为哪个 motive 服务”；
- 帮助 Stage2 判断“失败后是否仍应围绕同一 need 重翻译”；
- 帮助记忆系统以后总结“哪类动作在什么动机背景下有效”。

---

### 5.2 `action`

记录动作本身、抽象目标和具体实例地址。

```json
"action": {
  "skill_id": "gather",
  "raw_action": "Gather",
  "intent_family": "restore_satiety",
  "target": "refrigerator",
  "target_type": "object",
  "target_address": "the Ville:Hobbs Cafe:cafe:refrigerator",
  "resolved_target": "refrigerator",
  "resolution_kind": "known_object",
  "detail": "opening the refrigerator to gather food items"
}
```

#### 用途

- `Stage2` 用来生成“最近动作结果块”；
- 解析层用 `target + target_address` 做实例级冷却；
- 记忆系统用来生成描述、关键词和检索标签。

---

### 5.3 `execution`

记录本次执行发生了什么。

```json
"execution": {
  "result": "failed",
  "reason": "resource_empty",
  "reason_class": "resource_state",
  "can_execute": false,
  "phase": "on_arrival_precheck",
  "duration_ms": 0.46,
  "path_length": 1,
  "from_tile": [72, 19],
  "end_tile": [72, 19]
}
```

#### 建议的 `result`

- `success`
- `failed`
- `interrupted`

#### 建议的 `reason_class`

- `resource_state`
- `precondition`
- `navigation`
- `resolution`
- `social_constraint`
- `other`

#### 典型 reason 映射

| `reason` | `reason_class` | 含义 |
| :--- | :--- | :--- |
| `resource_empty` | `resource_state` | 资源实例为空 |
| `consume_no_food_available` | `precondition` | 背包/条件不满足 |
| `path_not_found` | `navigation` | 不可达 |
| `target_not_found` | `resolution` | 目标解析失败 |
| `invalid_food_source` | `resolution` | 目标语义不匹配 |

#### 用途

- Stage1：区分“是资源空了”还是“动作本身不可执行”；
- Stage2：决定后续翻译约束；
- 解析层：只有 `resource_state` 类失败适合做实例级 cooldown。

---

### 5.4 `effects`

记录动作的效果，不只包含自己，也应支持他人与关系变化。

```json
"effects": {
  "self_attribute_effects": {
    "satiety": 0.0,
    "stamina": 0.0,
    "health": 0.0,
    "mood": 0.0
  },
  "other_attribute_effects": {
    "Maria Lopez": {
      "mood": 4.0,
      "belonging": 3.0
    }
  },
  "relationship_effects": {
    "Maria Lopez": {
      "trust": 0.12
    }
  },
  "inventory_delta": {},
  "motive_effect_tags": [
    "satiety_attempt_failed",
    "no_progress",
    "resource_instance_empty"
  ],
  "progress_score": 0.0
}
```

#### 说明

- `self_attribute_effects`
  - 保持与现有 `attribute_effects` 兼容，优先覆盖自己四维核心状态：
    - `satiety`
    - `stamina`
    - `health`
    - `mood`
- `other_attribute_effects`
  - 用于社交、服务、帮助、伤害类 skill
- `relationship_effects`
  - 用于关系图、信任、亲密度等变化
- `inventory_delta`
  - 例如 `{"apple": +2}`
- `motive_effect_tags`
  - 用于提示词压缩、记忆关键词生成、分析
- `progress_score`
  - 统一表示“这次动作对当前目标需求的推进程度”

#### 为什么必须区分自己与他人

对记忆系统来说：

- `consume apple` 的价值主要是对自己的 `satiety`；
- `chat/comfort/give` 的价值可能主要体现在对他人的 `mood/belonging/trust`；

如果不区分，会导致社交经验难以被正确建模。

---

### 5.5 `resource_context`

用于资源实例识别和重规划。

```json
"resource_context": {
  "resource_type": "refrigerator",
  "resource_instance_key": "the ville:hobbs cafe:cafe:refrigerator",
  "resource_state_after": "empty",
  "same_type_alternatives_seen": [
    "the Ville:Dorm for Oak Hill College:kitchen:refrigerator"
  ]
}
```

#### 用途

- 解析层做实例级过滤；
- 经验摘要层说明“同类其他实例是否存在”；
- 为“允许冰箱A失败后转去冰箱B”提供依据。

---

## 6. 经验筛选：experience_scoring

执行结果不应无差别进入长期记忆。建议为每条 outcome 计算 `experience_scoring`。

```json
"experience_scoring": {
  "self_effect_magnitude": 0.88,
  "other_effect_magnitude": 0.00,
  "failure_learning_value": 0.72,
  "novelty_value": 0.30,
  "dominant_motive_alignment": 0.95,
  "base_significance": 0.81,
  "recency_weight": 1.0,
  "effective_score": 0.81,
  "should_promote_to_experience": true
}
```

### 6.1 字段含义

- `self_effect_magnitude`
  - 对自己四维状态的影响强度
- `other_effect_magnitude`
  - 对他人属性/动机的影响强度
- `failure_learning_value`
  - 即使失败，如果为未来提供了高价值约束，也应有较高分
- `novelty_value`
  - 是否是新实例、新情境、新路径
- `dominant_motive_alignment`
  - 与当前主动机是否高度相关
- `base_significance`
  - 仅基于事件本身的重要性
- `recency_weight`
  - 时间衰减权重
- `effective_score`
  - 最终经验有效分
- `should_promote_to_experience`
  - 是否晋升为长期经验记忆

### 6.2 评分思想

建议：

```text
effective_score = base_significance * recency_weight
```

其中：

```text
base_significance ≈
  self_effect_magnitude
  + other_effect_magnitude
  + failure_learning_value
  + novelty_value
  + dominant_motive_alignment
```

实际实现中可采用归一化加权和。

### 6.3 经验晋升阈值

建议分三档：

- `effective_score < 0.25`
  - 只写日志，不进入经验池
- `0.25 <= effective_score < 0.55`
  - 进入短期经验视图，不写长期记忆
- `effective_score >= 0.55`
  - 晋升为长期经验记忆，写入 `AssociativeMemory`

### 6.4 时效权重建议

建议基于 step 差值：

- `0~5` steps: `1.0`
- `6~15` steps: `0.7`
- `16~40` steps: `0.4`
- `40+` steps: `0.2`

如果某类记忆希望保留更久，例如强失败经验或重大社交经验，可单独调高保留权重。

---

## 7. 为什么“失败经验”也应进入筛选

失败不代表不重要。

下列失败经验具有高学习价值：

- `resource_empty`
  - 告诉系统某个具体资源实例当前不可用
- `consume_no_food_available`
  - 告诉系统当前不应再翻译成 `Consume`
- `path_not_found`
  - 告诉系统应切换路径或切换目标

因此，`failure_learning_value` 应当成为经验评分的重要组成部分。

---

## 8. 记忆系统适配：ActionExperienceMemory

现有记忆系统的核心载体是 `AssociativeMemory` 的 `ConceptNode`，它需要：

- `description`
- `keywords`
- `poignancy`
- `attribute_effects`
- `subject / predicate / object`

因此，`ActionOutcomeRecord` 不能直接作为记忆节点写入，必须投影为 `ActionExperienceMemory`。

### 8.1 建议结构

```json
"memory_projection": {
  "source_outcome_id": "outcome-uuid",
  "memory_type": "event",
  "subject": "Isabella Rodriguez",
  "predicate": "experienced",
  "object": "execution_result",
  "description": "Isabella Rodriguez found that the refrigerator at Hobbs Cafe was empty when trying to gather food.",
  "embedding_text": "Isabella Rodriguez found that the refrigerator at Hobbs Cafe was empty when trying to gather food.",
  "keywords": [
    "gather",
    "food",
    "refrigerator",
    "resource_empty",
    "empty",
    "failed",
    "restore_satiety",
    "hobbs cafe",
    "execution_result"
  ],
  "poignancy": 5.0,
  "attribute_effects": {
    "satiety": 0.0,
    "stamina": 0.0,
    "health": 0.0,
    "mood": 0.0
  },
  "memory_tags": {
    "skill_id": "gather",
    "target": "refrigerator",
    "target_address": "the Ville:Hobbs Cafe:cafe:refrigerator",
    "reason": "resource_empty",
    "dominant_motive": "satiety",
    "resource_instance_key": "the ville:hobbs cafe:cafe:refrigerator"
  }
}
```

### 8.2 记忆系统要求与满足关系

| 记忆系统需求 | 由哪个字段满足 |
| :--- | :--- |
| 可嵌入语义描述 | `memory_projection.description / embedding_text` |
| 检索关键词 | `memory_projection.keywords` |
| 记忆重要度 | `memory_projection.poignancy` |
| 动机效果排序 | `memory_projection.attribute_effects` |
| 结构化三元组 | `subject / predicate / object` |

### 8.3 为什么不直接把 outcome 写进 AssociativeMemory

因为原始 outcome 含大量运行时噪声字段：

- `decision_id`
- `phase`
- `duration_ms`
- `from_tile`
- `end_tile`
- `pipeline`

这些字段对 debug 有价值，但会污染 embedding 和检索质量。

---

## 9. 运行时聚合视图（Scratch Runtime Views）

建议在 `scratch` 中维护以下聚合态：

- `last_action_outcome`
- `recent_action_outcomes`
- `failed_resource_instances`
- `successful_resource_instances`

### 9.1 `last_action_outcome`

只保留最近一条 outcome，供 Stage1/Stage2 快速读取。

### 9.2 `recent_action_outcomes`

建议保留最近 `5~8` 条 outcome，用于：

- Stage1 的近期经验块
- Stage2 的最近动作结果块

### 9.3 `failed_resource_instances`

记录近期失败实例，用于解析层 cooldown。

示例：

```json
[
  {
    "target": "refrigerator",
    "target_address": "the Ville:Hobbs Cafe:cafe:refrigerator",
    "reason": "resource_empty",
    "curr_step": 161,
    "expires_after_step": 173
  }
]
```

### 9.4 `successful_resource_instances`

记录近期成功实例，用于解析层轻量 success bias。

示例：

```json
[
  {
    "target": "apple tree",
    "target_address": "the Ville:Johnson Park:park:apple tree",
    "progress_score": 0.5,
    "curr_step": 158,
    "expires_after_step": 178
  }
]
```

---

## 10. 三层消费方式

### 10.1 Stage1（demand_thinking）

Stage1 不需要完整 outcome JSON，而需要三个压缩块：

1. `LatestExecution`
2. `RecentRelevantOutcomes`
3. `ActionEffects`

示例：

```text
LatestExecution:
failed | gather | refrigerator | the Ville:Hobbs Cafe:cafe:refrigerator | reason=resource_empty

RecentRelevantOutcomes:
- failed | gather | refrigerator | the Ville:Hobbs Cafe:cafe:refrigerator | resource_empty
- success | gather | apple tree | the Ville:Johnson Park:park:apple tree | inventory+apple

ActionEffects:
- Consume(apple) directly restores satiety when inventory has apple.
- Gather(apple tree) can enable later eating.
- Repeating a failed empty refrigerator gives no progress.
```

#### Stage1 目标

- 调整下一步 immediate intent；
- 避免 thought 继续锁定刚失败的具体实例；
- 让成功经验影响“我接下来想去哪类目标”。

---

### 10.2 Stage2（action_translation）

Stage2 需要：

1. 最新失败/成功结果；
2. 近期动作经验块；
3. 翻译约束；
4. 当前 dominant motive 对应的 action effect hints。

示例：

```text
Recent Action Outcomes:
- failed | gather | refrigerator | the Ville:Hobbs Cafe:cafe:refrigerator | reason=resource_empty
- failed | consume | apple | inventory empty | reason=consume_no_food_available
- success | gather | apple tree | the Ville:Johnson Park:park:apple tree | effect=inventory+apple

Translation Constraints:
- Do not translate the same immediate need into the same failed resource instance again.
- Do not choose Consume unless the required food is currently available in inventory.
- If the same resource type still fits, prefer another feasible instance or another food source.
```

#### Stage2 目标

- 避免继续翻译成不可执行动作；
- 减少把 thought 再翻回失败目标类别；
- 让最近成功路径进入翻译偏好。

---

### 10.3 解析层（Resolver）

解析层应直接消费：

- `failed_resource_instances`
- `successful_resource_instances`
- 当前 `dominant_motive`

#### 解析原则

1. 先过滤 cooldown 中的失败实例；
2. 再优先近期成功实例；
3. 最后按距离选最近实例；
4. 如果同类实例全部失败，则允许切换到其他资源类别。

#### 解析层不应做的事

- 不应依赖 LLM 文本自己判断“这是同一个冰箱还是另一个冰箱”；
- 不应只按 `target` 名称做黑名单；
- 不应忽略 `target_address`。

---

## 11. 落盘方案

建议采用双写：

### 11.1 运行时内存态

写入 `scratch` 聚合视图：

- `last_action_outcome`
- `recent_action_outcomes`
- `failed_resource_instances`
- `successful_resource_instances`

### 11.2 全量 JSONL 日志

新增：

- `logs/action_outcome.jsonl`

每行格式：

```json
{
  "log": "action_outcome.jsonl",
  "persona": "Isabella Rodriguez",
  "curr_step": 161,
  "sim_time": "2026-07-10 08:12:20",
  "outcome": { ... ActionOutcomeRecord ... }
}
```

#### 为什么需要单独日志

- 便于训练数据准备；
- 便于行为回放和分析；
- 便于问题定位；
- 避免只依赖 `scratch.json` 的聚合态，丢失历史。

### 11.3 长期记忆写入

当 `experience_scoring.should_promote_to_experience = true` 时：

- 将 `memory_projection` 写入 `AssociativeMemory`
- 建议沿用现有 `record_execution_result_experience(...)` 模式扩展

---

## 12. 保留与过期策略

### 12.1 Scratch 内聚合

- `last_action_outcome`
  - 保留 1 条
- `recent_action_outcomes`
  - 保留最近 `5~8` 条
- `failed_resource_instances`
  - 默认 `8~12` steps 过期
- `successful_resource_instances`
  - 默认 `15~20` steps 过期

### 12.2 JSONL 日志

- 不删，全量保留

### 12.3 长期记忆

- 由 `poignancy + recency + relevance` 自然参与检索
- 不需要额外短期过期机制

---

## 13. 最小可用字段集合（MVP）

若先做最小实现，建议 outcome 至少包含以下字段：

```json
{
  "schema_version": 1,
  "outcome_id": "...",
  "persona": "...",
  "curr_step": 161,
  "decision_context": {
    "decision_id": "...",
    "dominant_motive": "satiety"
  },
  "action": {
    "skill_id": "gather",
    "target": "refrigerator",
    "target_address": "the Ville:Hobbs Cafe:cafe:refrigerator"
  },
  "execution": {
    "result": "failed",
    "reason": "resource_empty",
    "reason_class": "resource_state"
  },
  "effects": {
    "self_attribute_effects": {
      "satiety": 0.0,
      "stamina": 0.0,
      "health": 0.0,
      "mood": 0.0
    },
    "inventory_delta": {},
    "progress_score": 0.0
  },
  "resource_context": {
    "resource_instance_key": "the ville:hobbs cafe:cafe:refrigerator"
  },
  "experience_scoring": {
    "effective_score": 0.72,
    "should_promote_to_experience": true
  },
  "memory_projection": {
    "description": "...",
    "keywords": ["..."],
    "poignancy": 5.0,
    "subject": "...",
    "predicate": "experienced",
    "object": "execution_result"
  }
}
```

这个 MVP 已经足以支持：

- Stage1 / Stage2 的执行结果提示块；
- 解析层的实例级 cooldown；
- 长期记忆写入。

---

## 14. 不建议直接进入记忆嵌入文本的字段

以下字段对运行时很有价值，但不应直接进入 `memory_projection.description/embedding_text`：

- `decision_id`
- `pipeline`
- `wall_ts`
- `phase`
- `duration_ms`
- `from_tile`
- `end_tile`

原因：

- 会污染嵌入语义；
- 对检索帮助小；
- 对经验总结可读性差。

这些字段应保留在原始 outcome 里，用于调试和分析。

---

## 15. 与现有系统的兼容性建议

### 15.1 与 `AssociativeMemory` 兼容

保持：

- `attribute_effects` 仍以“四维自我属性”为核心；
- 对他人的变化单独存在 `other_attribute_effects`；

不要直接改造现有 `normalize_attribute_effects(...)` 的四维约束。

### 15.2 与 `intent_memory` 兼容

确保 `memory_projection.keywords` 中显式包含：

- 动作词：`gather / consume / chat / give`
- 目标词：`refrigerator / apple tree / bar / bed`
- 结果词：`failed / success / empty / inventory`
- 意图词：`restore_satiety / restore_mood / restore_stamina`

这样可直接匹配现有 [intent_memory.py](file:///Users/gun/mygame/generative_agents/reverie/backend_server/persona/cognitive_modules/intent_memory.py#L9-L29) 的关键词检索逻辑。

### 15.3 与当前提示词系统兼容

不要让 Stage1 / Stage2 直接消费完整 outcome JSON。

应由专门函数将 outcome 压缩为：

- `LatestExecution`
- `RecentRelevantOutcomes`
- `ActionEffects`
- `TranslationConstraints`

---

## 16. 推荐的开发顺序

1. **定义 `ActionOutcomeRecord` schema**
2. **技能执行结束统一产出 outcome**
3. **写 `logs/action_outcome.jsonl`**
4. **维护 scratch 聚合视图**
5. **实现 `experience_scoring`**
6. **实现 `memory_projection`**
7. **接入 Stage1 / Stage2**
8. **接入解析层实例级 cooldown 与 success bias**

---

## 17. 最终结论

本设计建议将技能执行结果正式定义为：

1. **原始执行事实：`ActionOutcomeRecord`**
2. **记忆投影：`ActionExperienceMemory`**
3. **运行时视图：Stage1 / Stage2 / Resolver 各自消费的压缩块**

其中：

- `ActionOutcomeRecord` 负责真实、完整、可回放；
- `ActionExperienceMemory` 负责长期记忆可写入、可检索、可摘要；
- `experience_scoring` 负责决定哪些结果值得晋升为经验；
- `target_address + resource_instance_key` 负责支持“同类资源可切换、同一实例不可重试”的关键能力。

换言之：

> 技能执行系统负责产出事实，记忆系统负责沉淀经验，提示词系统负责消费摘要，解析层负责执行硬约束。

