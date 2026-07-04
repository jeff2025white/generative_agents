# Task-Routed Model Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single task-routing model configuration layer so each LLM task type can select an appropriate provider/model version without hard-coding provider details in business logic.

**Architecture:** Keep provider credentials and raw model versions centralized in `llm_api_config.py`, then add a small task-type routing layer that maps task families such as decision, social chat, translation, and legacy prompt migration to named request configs. New prompt chains should read task routes, while legacy chains should be migrated incrementally to the same router instead of directly using `LOCAL_LLM_CONFIG` defaults.

**Tech Stack:** Python, OpenAI-compatible API routing, Ollama local inference, unittest

---

### Task 1: Add Task-Type Routing Constants

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\llm_api_config.py`
- Test: `g:\generative_agents\test\test_decision_request_config.py`

- [ ] **Step 1: Write the failing test**

```python
def test_task_route_names_default_to_expected_configs(self):
    self.assertEqual(TASK_ROUTE_CONFIG_NAMES["general_chat"], "zhipu_chat")
    self.assertEqual(TASK_ROUTE_CONFIG_NAMES["social_chat"], "zhipu_chat")
    self.assertEqual(TASK_ROUTE_CONFIG_NAMES["decision"], "zhipu_chat")
    self.assertEqual(TASK_ROUTE_CONFIG_NAMES["translation"], "zhipu_chat")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test.test_decision_request_config -v`
Expected: FAIL with `NameError` or missing `TASK_ROUTE_CONFIG_NAMES`

- [ ] **Step 3: Write minimal implementation**

```python
DEFAULT_PRIMARY_CLOUD_CONFIG_NAME = "zhipu_chat"

TASK_ROUTE_CONFIG_NAMES = {
    "general_chat": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
    "social_chat": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
    "decision": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
    "translation": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test.test_decision_request_config -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add reverie/backend_server/llm_api_config.py test/test_decision_request_config.py
git commit -m "feat: add task routed llm defaults"
```

### Task 2: Add Task Route Accessors

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\llm_api_config.py`
- Test: `g:\generative_agents\test\test_decision_request_config.py`

- [ ] **Step 1: Write the failing test**

```python
def test_get_task_route_request_config_returns_named_provider(self):
    self.assertEqual(
        get_task_route_request_config("decision"),
        get_request_config("zhipu_chat"),
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test.test_decision_request_config -v`
Expected: FAIL with missing `get_task_route_request_config`

- [ ] **Step 3: Write minimal implementation**

```python
def get_task_route_config_name(task_type):
    route_name = TASK_ROUTE_CONFIG_NAMES.get(task_type)
    if route_name is None:
        raise KeyError(f"Unknown task route: {task_type}")
    return route_name


def get_task_route_request_config(task_type):
    return get_request_config(get_task_route_config_name(task_type))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test.test_decision_request_config -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add reverie/backend_server/llm_api_config.py test/test_decision_request_config.py
git commit -m "feat: add llm task route accessors"
```

### Task 3: Rewire Default Accessors To Task Routes

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\llm_api_config.py`
- Test: `g:\generative_agents\test\test_decision_request_config.py`
- Test: `g:\generative_agents\test\test_chat_skill_guards.py`
- Test: `g:\generative_agents\test\test_translation_status_config.py`

- [ ] **Step 1: Write the failing test**

```python
def test_default_accessors_read_task_routes(self):
    self.assertEqual(
        get_default_cloud_chat_request_config(),
        get_task_route_request_config("general_chat"),
    )
    self.assertEqual(
        get_default_social_chat_request_config(),
        get_task_route_request_config("social_chat"),
    )
    self.assertEqual(
        get_default_decision_request_config(),
        get_task_route_request_config("decision"),
    )
    self.assertEqual(
        get_status_translation_config(),
        get_task_route_request_config("translation"),
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test.test_decision_request_config test.test_chat_skill_guards test.test_translation_status_config -v`
Expected: FAIL because accessors still read older default constants directly

- [ ] **Step 3: Write minimal implementation**

```python
def get_default_cloud_chat_request_config():
    return get_task_route_request_config("general_chat")


def get_default_social_chat_request_config():
    return get_task_route_request_config("social_chat")


def get_default_decision_request_config():
    return get_task_route_request_config("decision")


def get_status_translation_config():
    return get_task_route_request_config("translation")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test.test_decision_request_config test.test_chat_skill_guards test.test_translation_status_config -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add reverie/backend_server/llm_api_config.py test/test_decision_request_config.py test/test_chat_skill_guards.py test/test_translation_status_config.py
git commit -m "refactor: route llm defaults by task type"
```

### Task 4: Migrate Legacy Event-Triple Route

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\persona\prompt_template\run_gpt_prompt.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py`
- Test: `g:\generative_agents\test\test_event_triple_request_config.py`

- [ ] **Step 1: Write the failing test**

```python
def test_event_triple_uses_translation_route_request_config(self):
    config = {"api_key": "cloud-key", "api_base": "https://api.example/v1", "model": "glm-4-flash"}
    with patch.object(prompt_module, "ChatGPT_safe_generate_response") as mocked, \
         patch.object(prompt_module, "generate_prompt", return_value="prompt"):
        prompt_module.run_gpt_prompt_event_triple("walks home", persona, request_config=config)
    self.assertEqual(mocked.call_args.kwargs["request_config"], config)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test.test_event_triple_request_config -v`
Expected: FAIL because `run_gpt_prompt_event_triple()` still uses `safe_generate_response()`

- [ ] **Step 3: Write minimal implementation**

```python
def run_gpt_prompt_event_triple(action_description, persona, verbose=False, request_config=None):
    output = ChatGPT_safe_generate_response(
        prompt,
        example_output,
        special_instruction,
        repeat=2,
        fail_safe_response=get_fail_safe(),
        func_validate=__func_validate,
        func_clean_up=__func_clean_up,
        verbose=verbose,
        prompt_kind="event_triple",
        metadata={"prompt_template": prompt_template},
        request_config=request_config,
    )
    return output
```

```python
event_triple_request_config = get_status_translation_config()
return run_gpt_prompt_event_triple(act_desp, persona, request_config=event_triple_request_config)[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test.test_event_triple_request_config -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add reverie/backend_server/persona/prompt_template/run_gpt_prompt.py reverie/backend_server/persona/cognitive_modules/plan.py test/test_event_triple_request_config.py
git commit -m "fix: route event triple through task config"
```

### Task 5: Run Regression Checks

**Files:**
- Test: `g:\generative_agents\test\test_decision_request_config.py`
- Test: `g:\generative_agents\test\test_chat_skill_guards.py`
- Test: `g:\generative_agents\test\test_translation_status_config.py`
- Test: `g:\generative_agents\test\test_joint_decision_pipeline.py`
- Test: `g:\generative_agents\test\test_event_triple_request_config.py`

- [ ] **Step 1: Run targeted regression suite**

Run: `python -m unittest test.test_decision_request_config test.test_chat_skill_guards test.test_translation_status_config test.test_joint_decision_pipeline test.test_event_triple_request_config`
Expected: PASS

- [ ] **Step 2: Review route matrix**

```python
assert get_task_route_config_name("general_chat") == "zhipu_chat"
assert get_task_route_config_name("social_chat") == "zhipu_chat"
assert get_task_route_config_name("decision") == "zhipu_chat"
assert get_task_route_config_name("translation") == "zhipu_chat"
```

- [ ] **Step 3: Commit**

```bash
git add reverie/backend_server/llm_api_config.py reverie/backend_server/persona/prompt_template/run_gpt_prompt.py reverie/backend_server/persona/cognitive_modules/plan.py test/test_decision_request_config.py test/test_chat_skill_guards.py test/test_translation_status_config.py test/test_event_triple_request_config.py
git commit -m "test: cover task routed llm configuration"
```
