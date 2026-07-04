"""Centralized LLM provider and API key configuration."""

LOCAL_LLM_CONFIG = {
    "api_key": "ollama",
    "api_base": "http://localhost:11434/v1",
    "model": "deepseek-r1:7b",
}

DEEPSEEK_CHAT_REQUEST_CONFIG = {
    "api_key": "sk-f7775909e210487eb449ee89cef77126",
    "api_base": "https://api.deepseek.com/v1",
    "model": "deepseek-v4-flash",
}

ZHIPU_CHAT_REQUEST_CONFIG = {
    "api_key": "b1cd40c82d59411b81071d190a0badb7.voukUXlnTWEx44Li",
    "api_base": "https://open.bigmodel.cn/api/paas/v4/",
    "model": "glm-4-flash",
}

BAILIAN_CHAT_REQUEST_CONFIG = {
    "api_key": "sk-ws-H.RXEXPRM.V7xV.MEUCIQCX_Ht-mq4d9JvazH5E1ylm78Ethrks6UmDyOsEzEfdiAIgQ68FlOQTwKKExJ5pfftcJC8c3wI7n9DG9lU6Aevbvmk",
    "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-plus-character",
}

_REQUEST_CONFIGS = {
    "local": LOCAL_LLM_CONFIG,
    "deepseek_chat": DEEPSEEK_CHAT_REQUEST_CONFIG,
    "zhipu_chat": ZHIPU_CHAT_REQUEST_CONFIG,
    "bailian_chat": BAILIAN_CHAT_REQUEST_CONFIG,
}

# Single-switch default cloud provider. Update this one name to change the
# system-wide cloud model used by chat, social, decision, and status flows.
DEFAULT_PRIMARY_CLOUD_CONFIG_NAME = "zhipu_chat"
DEFAULT_CLOUD_CHAT_CONFIG_NAME = DEFAULT_PRIMARY_CLOUD_CONFIG_NAME
DEFAULT_SOCIAL_CHAT_CONFIG_NAME = DEFAULT_PRIMARY_CLOUD_CONFIG_NAME
DEFAULT_DECISION_CONFIG_NAME = DEFAULT_PRIMARY_CLOUD_CONFIG_NAME

# Task-routed LLM config map. Update individual values only when a specific
# task family needs a different provider/model version than the primary default.
TASK_ROUTE_CONFIG_NAMES = {
    "general_chat": DEFAULT_CLOUD_CHAT_CONFIG_NAME,
    "social_chat": DEFAULT_SOCIAL_CHAT_CONFIG_NAME,
    "social_decision": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
    "social_generation": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
    "safety_scoring": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
    "decision": DEFAULT_DECISION_CONFIG_NAME,
    "planning": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
    "location_selection": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
    "object_state": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
    "memory_reflection": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
    "translation": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
    "event_triple": DEFAULT_PRIMARY_CLOUD_CONFIG_NAME,
}


def get_request_config(config_name):
    """Return a defensive copy of the named request config."""
    config = _REQUEST_CONFIGS.get(config_name)
    if config is None:
        raise KeyError(f"Unknown request config: {config_name}")
    return dict(config)


def get_task_route_config_name(task_type):
    """Return the named provider config assigned to the given task type."""
    route_name = TASK_ROUTE_CONFIG_NAMES.get(task_type)
    if route_name is None:
        raise KeyError(f"Unknown task route: {task_type}")
    return route_name


def get_task_route_request_config(task_type):
    """Return a defensive copy of the request config for the task type."""
    return get_request_config(get_task_route_config_name(task_type))


def get_default_cloud_chat_request_config():
    """Return the project-wide default cloud chat provider config."""
    return get_task_route_request_config("general_chat")


def get_default_social_chat_request_config():
    """Return the preferred cloud config for NPC social chat generation."""
    return get_task_route_request_config("social_chat")


def get_default_decision_request_config():
    """Return the preferred cloud config for high-value decision prompts."""
    return get_task_route_request_config("decision")


def get_default_translation_request_config():
    """Return the preferred cloud config for translation-like tasks."""
    return get_task_route_request_config("translation")


def get_status_translation_config():
    """Return the preferred config for frontend status translation."""
    return get_default_translation_request_config()
