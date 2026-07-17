import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if "openai" not in sys.modules:
    sys.modules["openai"] = SimpleNamespace(
        api_key=None,
        api_base=None,
        ChatCompletion=SimpleNamespace(create=lambda **kwargs: {"choices": [{"message": {"content": "stub"}}]}),
        Embedding=SimpleNamespace(create=lambda **kwargs: {"data": [{"embedding": [1.0, 0.0]}]}),
    )

if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda a: sum(x * x for x in a) ** 0.5
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub

from object_affordances import ObjectAffordanceRegistry, default_registry
from persona.cognitive_modules.food_sources import is_valid_gather_food_source
from persona.cognitive_modules.plan import _build_static_resource_context_text
from persona.cognitive_modules.stage1_prompt_compiler import build_motive_grouped_skill_list
from persona.cognitive_modules.stage1_prompt_compiler import build_motive_grouped_experience_list
from persona.cognitive_modules.intent_memory import summarize_memories_by_motives


class ObjectAffordanceRegistryTests(unittest.TestCase):
    def test_food_affordance_lookup(self):
        self.assertTrue(default_registry.has_affordance("refrigerator", "satiety", "can_gather_food"))
        self.assertFalse(default_registry.has_affordance("bed", "satiety", "can_gather_food"))
        self.assertGreaterEqual(
            len(default_registry.find_objects_by_affordance("satiety", "can_gather_food")), 4
        )

    def test_json_only_extension_is_discovered(self):
        config_path = ROOT / "reverie" / "backend_server" / "object_properties.json"
        registry = ObjectAffordanceRegistry(config_path)
        self.assertTrue(registry.has_affordance("vending machine", "satiety", "can_gather_food"))
        self.assertEqual(registry.get_purpose_text("vending machine"), "可购买零食")
        self.assertEqual(
            registry.get_gather_description("apple tree"),
            "gathering apples from the apple tree",
        )

    def test_food_source_aliases_remain_compatible(self):
        self.assertTrue(is_valid_gather_food_source("fridge"))
        self.assertTrue(is_valid_gather_food_source("behind the cafe counter"))

    def test_resource_prompt_lists_each_object_once_with_motive_tags(self):
        class FakeMaze:
            maze_name = "test"
            address_tiles = {
                "the Ville:home:kitchen:refrigerator": {(0, 0)},
                "the Ville:home:bedroom:bed": {(1, 0)},
                "the Ville:home:music:piano": {(2, 0)},
            }

            @staticmethod
            def access_tile(tile):
                return {"collision": False}

        text = _build_static_resource_context_text(None, FakeMaze(), dominant_motive="satiety")
        self.assertIn("WorldResourceCatalogue", text)
        self.assertIn("refrigerator[satiety]:可获取 / 储存食物", text)
        self.assertIn("bed[stamina,health]:休息 / 恢复体力", text)
        self.assertEqual(text.count("refrigerator["), 1)

    def test_skill_prompt_groups_configured_categories_by_motive(self):
        text = build_motive_grouped_skill_list("satiety")
        self.assertIn("MotiveActionIndex（仅索引，不筛选动作）", text)
        self.assertIn("饱食 / 食物/satiety=[Consume,Gather]", text)
        self.assertIn("精力 / 休息/stamina=[Rest,Idle]", text)

    def test_memory_prompt_groups_primary_secondary_and_other_relevance(self):
        memories = [
            SimpleNamespace(description="Gathering food from the refrigerator worked.", attribute_effects={"satiety": 20}),
            SimpleNamespace(description="The refrigerator was empty.", attribute_effects={"satiety": -1}),
            SimpleNamespace(description="A chat with Maria eased loneliness.", attribute_effects={"belonging": 8}),
            SimpleNamespace(description="The chat with Maria failed.", attribute_effects={"belonging": -1}),
            SimpleNamespace(description="Studying at the desk improved my skills.", attribute_effects={"competence": 4}),
        ]
        text = summarize_memories_by_motives(memories, "satiety", "belonging")
        self.assertIn("主导动机相关（饱食 / 食物 / satiety）:", text)
        self.assertIn("⭐ Gathering food from the refrigerator worked.", text)
        self.assertIn("成功经验:", text)
        self.assertIn("失败尝试（避免重复）:", text)
        self.assertIn("⚠ The refrigerator was empty.", text)
        self.assertIn("次要动机相关（归属 / 社交 / belonging）:", text)
        self.assertIn("其他可参考经验:", text)

    def test_instance_experience_groups_primary_and_secondary_motives(self):
        units = [
            {"experience_kind": "prefer", "intent_family": "restore_satiety", "evidence_summary": "apple tree worked."},
            {"experience_kind": "avoid", "intent_family": "restore_satiety", "evidence_summary": "fridge was empty."},
            {"experience_kind": "prefer", "intent_family": "communication", "evidence_summary": "Maria was welcoming."},
        ]
        persona = SimpleNamespace(scratch=SimpleNamespace(get_experience_priority_units=lambda: units))
        text = build_motive_grouped_experience_list(persona, "satiety", "belonging")
        self.assertIn("主导动机相关（satiety）:", text)
        self.assertIn("⚠ - fridge was empty.", text)
        self.assertIn("次要动机相关（belonging）:", text)


if __name__ == "__main__":
    unittest.main()
