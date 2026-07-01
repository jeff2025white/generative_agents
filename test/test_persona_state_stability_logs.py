import json
import sys
import tempfile
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch
from types import ModuleType, SimpleNamespace


ROOT = Path(r"g:\generative_agents")
BACKEND_ROOT = ROOT / "environment" / "frontend_server"


def load_views_module():
    global_methods_module = sys.modules.setdefault("global_methods", ModuleType("global_methods"))
    if not hasattr(global_methods_module, "check_if_file_exists"):
        global_methods_module.check_if_file_exists = lambda path: False
    sys.modules.setdefault("requests", ModuleType("requests"))

    django_module = sys.modules.setdefault("django", ModuleType("django"))
    shortcuts_module = sys.modules.setdefault("django.shortcuts", ModuleType("django.shortcuts"))
    shortcuts_module.render = lambda request, template, context: {"template": template, "context": context}
    shortcuts_module.redirect = lambda *args, **kwargs: None
    shortcuts_module.HttpResponseRedirect = lambda *args, **kwargs: None
    http_module = sys.modules.setdefault("django.http", ModuleType("django.http"))
    http_module.HttpResponse = SimpleNamespace
    http_module.JsonResponse = SimpleNamespace
    csrf_module = sys.modules.setdefault("django.views.decorators.csrf", ModuleType("django.views.decorators.csrf"))
    csrf_module.csrf_exempt = lambda fn: fn

    translator_package = sys.modules.setdefault("translator", ModuleType("translator"))
    translator_package.__path__ = [str(BACKEND_ROOT / "translator")]
    models_module = sys.modules.setdefault("translator.models", ModuleType("translator.models"))
    models_module.__all__ = []

    module_name = "translator.views_runtime"
    if module_name in sys.modules:
        return sys.modules[module_name]

    module_path = BACKEND_ROOT / "translator" / "views.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


views = load_views_module()


class PersonaStateStabilityLogTests(unittest.TestCase):
    def test_load_recent_decision_stability_logs_filters_persona_and_event(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_path = Path(tmp_dir) / "decision_stability.jsonl"
            rows = [
                {"persona": "Maria Lopez", "event": "switch_blocked", "curr_step": 10},
                {"persona": "Maria Lopez", "event": "action_completed", "curr_step": 11},
                {"persona": "Klaus Mueller", "event": "switch_blocked", "curr_step": 12},
                {"persona": "Maria Lopez", "event": "irrelevant_event", "curr_step": 13},
            ]
            with open(logs_path, "w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

            with patch.object(views.os.path, "abspath", return_value=str(logs_path)):
                loaded = views._load_recent_decision_stability_logs("Maria Lopez", limit=10)

        self.assertEqual(len(loaded), 2)
        self.assertEqual([row["event"] for row in loaded], ["switch_blocked", "action_completed"])

    def test_translate_recent_decision_stability_logs_adds_translated_signatures(self):
        logs = [
            {
                "event": "switch_blocked",
                "old_signature": {"skill_id": "work", "target": "desk", "intent_family": "work"},
                "new_signature": {"skill_id": "chat with", "target": "Maria Lopez", "intent_family": "communication"},
                "description": "chatting with Maria Lopez",
                "source": "social_trigger",
            },
            {
                "event": "action_completed",
                "signature": {"skill_id": "gather", "target": "refrigerator", "intent_family": "restore_satiety"},
            },
        ]

        translated = views._translate_recent_decision_stability_logs(logs, translate_func=lambda text: f"ZH:{text}")

        self.assertEqual(translated[0]["old_signature_zh"]["skill_id"], "ZH:work")
        self.assertEqual(translated[0]["new_signature_zh"]["intent_family"], "ZH:communication")
        self.assertEqual(translated[0]["description_zh"], "ZH:chatting with Maria Lopez")
        self.assertEqual(translated[1]["signature_zh"]["target"], "ZH:refrigerator")


if __name__ == "__main__":
    unittest.main()
