# 任务路由 LLM 配置说明

## 目标

项目现在使用“任务类型 -> 配置名 -> 实际模型”的中心路由方式。

这样做的目的有两个：

1. 以后切换云模型时，只改配置中心，不改业务代码。
2. 不同类型任务可以逐步拆分到不同模型版本，避免所有链路共用一个版本。

## 核心入口

主配置文件：

- `g:\generative_agents\reverie\backend_server\llm_api_config.py`

关键结构：

- `_REQUEST_CONFIGS`
  作用：维护“配置名 -> api_key/api_base/model”的原始配置。

- `DEFAULT_PRIMARY_CLOUD_CONFIG_NAME`
  作用：全局默认云模型总开关。

- `TASK_ROUTE_CONFIG_NAMES`
  作用：维护“任务类型 -> 配置名”的中心路由表。

- `get_task_route_request_config(task_type)`
  作用：调用方按任务类型取最终请求配置。

## 当前配置名

- `local`
  本地 Ollama，当前模型：`deepseek-r1:7b`

- `zhipu_chat`
  智谱云，当前模型：`glm-4-flash`

- `deepseek_chat`
  DeepSeek 云，当前模型：`deepseek-v4-flash`

- `bailian_chat`
  百炼云，当前模型：`qwen-plus-character`

## 当前任务路由

- `general_chat`
  普通云聊天默认入口

- `social_chat`
  NPC 社交聊天

- `social_decision`
  是否发起对话、如何反应等社交决策

- `social_generation`
  生成对话正文、逐轮对话 utterance

- `safety_scoring`
  安全评分与内容风险判断

- `decision`
  高价值决策链

- `planning`
  作息规划、日程拆解、时间安排

- `location_selection`
  位置、区域、对象选择

- `object_state`
  物体状态描述

- `memory_reflection`
  关键词提取、对话总结、反思、poignancy、memo

- `translation`
  翻译、状态文案转换

- `event_triple`
  动作或对象事件三元组

## 如何切换

### 1. 全局切换默认云模型

改这里：

```python
DEFAULT_PRIMARY_CLOUD_CONFIG_NAME = "zhipu_chat"
```

适用场景：

- 大多数任务都想统一切回 DeepSeek
- 或者统一切到百炼

### 2. 只切某一类任务

改这里：

```python
TASK_ROUTE_CONFIG_NAMES = {
    "decision": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
    "planning": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
    "memory_reflection": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
}
```

例如：

```python
TASK_ROUTE_CONFIG_NAMES["decision"] = "deepseek_chat"
TASK_ROUTE_CONFIG_NAMES["translation"] = "zhipu_chat"
TASK_ROUTE_CONFIG_NAMES["social_generation"] = "bailian_chat"
```

## 推荐策略

如果优先考虑稳定和统一：

- `decision -> zhipu_chat`
- `planning -> zhipu_chat`
- `memory_reflection -> zhipu_chat`
- `translation -> zhipu_chat`

如果想分工更细：

- `decision -> deepseek_chat`
- `planning -> zhipu_chat`
- `social_generation -> bailian_chat`
- `memory_reflection -> zhipu_chat`
- `translation -> zhipu_chat`

## 代码接入原则

新函数应优先使用：

```python
request_config = request_config or get_task_route_request_config("task_type")
```

不要再直接写死：

- `LOCAL_LLM_CONFIG`
- `gpt35_model`
- `gpt4_model`
- `ChatGPT_safe_generate_response_OLD`
- `safe_generate_response()`

## 当前状态

`run_gpt_prompt.py` 的活跃主链函数已经基本接入任务路由体系。

后续如果还新增 prompt：

1. 先判断它属于哪一类任务
2. 放进 `TASK_ROUTE_CONFIG_NAMES`
3. 用对应任务类型读取 `request_config`
4. 补一条默认路由测试
