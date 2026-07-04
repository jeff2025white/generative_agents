# Decision Cloud Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `decide_demand_action()` 主链中的需求思考、联合决策、动作翻译三段 LLM 调用显式切到云模型，同时保留其他默认链路继续走本地。

**Architecture:** 不修改全局默认 `LOCAL_LLM_CONFIG`，而是在 `llm_api_config.py` 增加“决策专用云配置”入口，并由 `_run_decision_pipeline()` 在一次决策内解析同一份 `request_config`，向下传递到 `run_gpt_prompt_demand_thinking()`、`run_gpt_prompt_joint_decision()`、`run_gpt_prompt_action_translation()`。这样可以把高价值高风险决策链路单独上云，同时保留 embedding、本地回退、旧反思链路不变。

**Tech Stack:** Python, OpenAI-compatible request routing, unittest, Ollama + cloud provider split routing

---

### Task 1: Add Decision Routing Config

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\llm_api_config.py`
- Test: `g:\generative_agents\test\test_decision_request_config.py`

- [ ] **Step 1: Add a decision-specific default config getter**

```python
DEFAULT_DECISION_CONFIG_NAME = "deepseek_chat"


def get_default_decision_request_config():
    """Return the preferred cloud config for high-value decision prompts."""
    return get_request_config(DEFAULT_DECISION_CONFIG_NAME)
```

- [ ] **Step 2: Add a focused config test**

```python
from llm_api_config import get_default_decision_request_config, get_request_config


def test_decision_request_config_defaults_to_deepseek_chat(self):
    self.assertEqual(
        get_default_decision_request_config(),
        get_request_config("deepseek_chat"),
    )
```

- [ ] **Step 3: Run targeted test**

Run: `python -m unittest test.test_decision_request_config -v`
Expected: PASS

### Task 2: Thread Cloud Routing Through Decision Prompt Wrappers

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py`
- Test: `g:\generative_agents\test\test_action_translation_convergence.py`
- Test: `g:\generative_agents\test\test_joint_decision_pipeline.py`

- [ ] **Step 1: Extend function signatures**

```python
def run_gpt_prompt_demand_thinking(..., decision_id=None, request_config=None):
def run_gpt_prompt_joint_decision(..., decision_id=None, request_config=None):
def run_gpt_prompt_action_translation(..., decision_id=None, persona=None, request_config=None):
```

- [ ] **Step 2: Pass request_config into the LLM helpers**

```python
output = ChatGPT_request(
    prompt,
    prompt_kind="demand_thinking",
    metadata={...},
    request_config=request_config,
)

output = ChatGPT_safe_generate_response(
    ...,
    prompt_kind="joint_decision",
    metadata={...},
    request_config=request_config,
)
```

- [ ] **Step 3: Add wrapper-level tests**

```python
def test_joint_decision_forwards_request_config(self):
    config = {"api_key": "cloud-key", "api_base": "https://api.example/v1", "model": "cloud-model"}
    captured = {}

    def fake_safe_generate_response(*args, **kwargs):
        captured["request_config"] = kwargs.get("request_config")
        return {...}
```

- [ ] **Step 4: Run targeted tests**

Run: `python -m unittest test.test_joint_decision_pipeline test.test_action_translation_convergence -v`
Expected: PASS

### Task 3: Route Decision Pipeline to Cloud Only

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py`
- Test: `g:\generative_agents\test\test_joint_decision_pipeline.py`

- [ ] **Step 1: Resolve the decision config once per pipeline execution**

```python
decision_request_config = get_default_decision_request_config()
```

- [ ] **Step 2: Forward the same config to all decision stages**

```python
joint_result = run_gpt_prompt_joint_decision(..., request_config=decision_request_config)
thinking_text = run_gpt_prompt_demand_thinking(..., request_config=decision_request_config)
decision = run_gpt_prompt_action_translation(..., request_config=decision_request_config)
```

- [ ] **Step 3: Add pipeline-level tests**

```python
with patch.object(plan_module, "get_default_decision_request_config", return_value=config):
    ...
    thinking_mock.assert_called_once()
    self.assertEqual(thinking_mock.call_args.kwargs["request_config"], config)
```

- [ ] **Step 4: Run targeted tests**

Run: `python -m unittest test.test_joint_decision_pipeline -v`
Expected: PASS

### Task 4: Final Verification

**Files:**
- Modify: `g:\generative_agents\docs\superpowers\plans\2026-07-03-decision-cloud-routing.md`

- [ ] **Step 1: Run the full focused suite**

Run: `python -m unittest test.test_decision_request_config test.test_joint_decision_pipeline test.test_action_translation_convergence test.test_translation_status_config -v`
Expected: PASS

- [ ] **Step 2: Confirm no local default changes leaked**

Run: `python - <<'PY'\nfrom llm_api_config import LOCAL_LLM_CONFIG, get_default_decision_request_config\nprint(LOCAL_LLM_CONFIG['model'])\nprint(get_default_decision_request_config()['model'])\nPY`
Expected: first line is `deepseek-r1:7b`, second line is cloud decision model

- [ ] **Step 3: Commit**

```bash
git add reverie/backend_server/llm_api_config.py reverie/backend_server/persona/prompt_template/run_gpt_prompt.py reverie/backend_server/persona/cognitive_modules/plan.py test/test_decision_request_config.py test/test_joint_decision_pipeline.py test/test_action_translation_convergence.py docs/plans/2026-07-03-decision-cloud-routing.md
git commit -m "feat: route decision pipeline to cloud config"
```
