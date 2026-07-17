import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sys.modules.setdefault("openai", SimpleNamespace(api_key=None, api_base=None))
if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.dot = lambda *args, **kwargs: 0.0
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda *args, **kwargs: 1.0
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub

from persona.cognitive_modules.stage1_prompt_compiler import (
    _build_other_people_social_leverage_text,
    build_background_identity_text,
    build_decision_social_context_text,
    remember_known_persona_profile,
    refresh_prompt_profile_from_planning,
    refresh_prompt_profile_from_reflection,
)
from persona.cognitive_modules.motive_selector import build_default_motive_attributes
from persona.memory_structures.scratch import Scratch


class Stage1PromptProfileRefreshTests(unittest.TestCase):
    def _make_thought(self, description, *, poignancy=8.0, keywords=None, hours_ago=0, depth=1, filling=None):
        return SimpleNamespace(
            description=description,
            embedding_key=description,
            poignancy=poignancy,
            keywords=set(keywords or []),
            created=datetime(2026, 7, 9, 8, 0, 0) if hours_ago == 0 else datetime(2026, 7, 9, 8, 0, 0),
            depth=depth,
            filling=filling or [],
        )

    def _build_persona(self):
        scratch = Scratch(str(ROOT / "test" / "__missing_stage1_profile__.json"))
        scratch.name = "Maria Lopez"
        scratch.first_name = "Maria"
        scratch.age = 31
        scratch.innate = "friendly, outgoing"
        scratch.learned = "good at serving customers and organizing the cafe"
        scratch.currently = "Maria is preparing for another busy day at Hobbs Cafe."
        scratch.lifestyle = "wakes early and keeps a regular cafe routine"
        scratch.daily_plan_req = "Open the cafe, serve guests, and rest at night."
        scratch.daily_req = [
            "open Hobbs Cafe at 8:00 am",
            "serve lunch customers at noon",
            "close the cafe in the evening",
        ]
        scratch.curr_time = datetime(2026, 7, 9, 8, 0, 0)
        scratch.act_start_time = datetime(2026, 7, 9, 8, 0, 0)
        a_mem = SimpleNamespace(
            seq_thought=[
                self._make_thought(
                    "For Maria Lopez's planning: I should keep the cafe running smoothly through the lunch rush.",
                    keywords={"planning", "cafe", "serve"},
                    poignancy=8.5,
                    depth=2,
                    filling=["node_1", "node_2"],
                ),
                self._make_thought(
                    "Maria Lopez realizes her friendship with Klaus Mueller makes the cafe feel more stable.",
                    keywords={"friend", "relationship", "klaus"},
                    poignancy=7.5,
                    depth=2,
                    filling=["node_3"],
                ),
                self._make_thought(
                    "Maria Lopez wants to stay useful at the cafe and protect a steady routine.",
                    keywords={"work", "cafe", "routine"},
                    poignancy=9.0,
                    depth=3,
                    filling=["node_4", "node_5"],
                ),
            ],
            social_relationship_graph={
                "relations": {
                    "Klaus Mueller": {
                        "relationship": "friend",
                        "trust": 0.82,
                        "recent_events": ["shared lunch plans"],
                    },
                    "Isabella Rodriguez": {
                        "relationship": "coworker",
                        "trust": 0.91,
                        "recent_events": ["coordinated cafe shift"],
                    },
                }
            }
        )
        return SimpleNamespace(name="Maria Lopez", scratch=scratch, a_mem=a_mem)

    def _build_llm_enabled_persona(self):
        persona = self._build_persona()
        persona.enable_llm_profile_summaries = True
        persona.a_mem.id_to_node = {"node_1": object()}
        return persona

    def _build_target_persona(self):
        scratch = Scratch(str(ROOT / "test" / "__missing_stage1_target__.json"))
        scratch.name = "Klaus Mueller"
        scratch.first_name = "Klaus"
        scratch.age = 28
        scratch.innate = "kind, inquisitive, calm"
        scratch.learned = "good at research and patient conversation"
        scratch.curr_time = datetime(2026, 7, 9, 8, 0, 0)
        scratch.act_start_time = datetime(2026, 7, 9, 8, 0, 0)
        scratch.get_motive_attributes_snapshot = lambda: build_default_motive_attributes(
            overrides={
                "satiety": {"current_value": 38.0},
                "mood": {"current_value": 49.0},
                "stamina": {"current_value": 80.0},
                "health": {"current_value": 92.0},
            }
        )
        return SimpleNamespace(name="Klaus Mueller", scratch=scratch, a_mem=SimpleNamespace())

    def test_refresh_from_planning_updates_daily_and_social_fields(self):
        persona = self._build_persona()

        changed = refresh_prompt_profile_from_planning(persona, source="unit_test_planning")

        self.assertTrue(changed)
        self.assertEqual(
            persona.scratch.get_prompt_profile_field("daily_plan_text"),
            "Open the cafe, serve guests, and rest at night.",
        )
        social_text = persona.scratch.get_prompt_profile_field("social_relationships_text")
        self.assertIn("Isabella Rodriguez", social_text)
        self.assertIn("coworker", social_text)
        self.assertEqual(
            persona.scratch.prompt_profile["fields"]["daily_plan_text"]["source"],
            "unit_test_planning",
        )

    def test_refresh_from_reflection_appends_reflection_context(self):
        persona = self._build_persona()
        refresh_prompt_profile_from_planning(persona, source="unit_test_planning")

        refresh_prompt_profile_from_reflection(
            persona,
            planning_thought="For Maria Lopez's planning: I should protect the lunch rush and keep the cafe running smoothly.",
            memo_thought="Maria Lopez feels she can rely on Klaus Mueller when the cafe gets hectic.",
            source="unit_test_reflection",
        )

        current_situation = persona.scratch.get_prompt_profile_field("current_situation_text")
        social_text = persona.scratch.get_prompt_profile_field("social_relationships_text")
        self.assertIn("Recent reflection signals:", current_situation)
        self.assertIn("keep the cafe running smoothly", current_situation)
        self.assertIn("最近社交反思", social_text)
        self.assertIn("Klaus Mueller", social_text)
        self.assertEqual(
            persona.scratch.prompt_profile["fields"]["social_relationships_text"]["source"],
            "unit_test_reflection",
        )
        long_term_goals = persona.scratch.get_prompt_profile_field("long_term_goals_text")
        self.assertIn("stay alive", long_term_goals.lower())
        self.assertIn("responsibilities", long_term_goals.lower())
        self.assertTrue("relationships" in long_term_goals.lower() or "steady" in long_term_goals.lower())

    def test_social_summary_uses_runtime_persona_innate_traits_and_caches_them(self):
        persona = self._build_persona()
        target_persona = self._build_target_persona()
        persona.runtime_known_personas = {target_persona.name: target_persona}

        changed = refresh_prompt_profile_from_planning(persona, source="unit_test_social_runtime")

        self.assertTrue(changed)
        social_text = persona.scratch.get_prompt_profile_field("social_relationships_text")
        self.assertIn("Klaus Mueller", social_text)
        self.assertIn("Klaus Mueller: 亲密程度=0.82", social_text)
        cached = persona.scratch.personal_knowledge["persona_profiles"]["Klaus Mueller"]
        self.assertEqual(cached["innate_traits_text"], "kind, inquisitive, calm")

    def test_other_people_text_uses_runtime_persona_names_and_innate_traits(self):
        persona = self._build_persona()
        target_persona = self._build_target_persona()
        persona.runtime_known_personas = {
            target_persona.name: target_persona,
            "Isabella Rodriguez": SimpleNamespace(
                name="Isabella Rodriguez",
                scratch=SimpleNamespace(
                    innate="warm, sociable, imaginative",
                    get_prompt_profile_field=lambda field_name: "warm, sociable, imaginative" if field_name == "innate_traits_text" else "",
                    get_motive_attributes_snapshot=lambda: build_default_motive_attributes(
                        overrides={
                            "mood": {"current_value": 41.0},
                            "belonging": {"current_value": 48.0},
                            "satiety": {"current_value": 78.0},
                            "stamina": {"current_value": 84.0},
                            "health": {"current_value": 95.0},
                        }
                    ),
                ),
            ),
        }

        decision_social_text = build_decision_social_context_text(persona)
        background_identity = build_background_identity_text(persona)
        predicted_behavior_text = _build_other_people_social_leverage_text(persona)

        self.assertIn("Klaus Mueller: 亲密程度=0.82", decision_social_text)
        self.assertIn("Isabella Rodriguez: 亲密程度=0.91", decision_social_text)
        self.assertNotIn("Other People / Predicted Behavior:", background_identity)
        self.assertIn("Other People / Power Map", predicted_behavior_text)
        self.assertIn("- Klaus Mueller", predicted_behavior_text)
        self.assertIn("- Isabella Rodriguez", predicted_behavior_text)
        self.assertIn("motives=satiety/mood", predicted_behavior_text)
        self.assertIn("predicted=", predicted_behavior_text)
        self.assertIn("assets=", predicted_behavior_text)
        self.assertIn("possible_interactions=", predicted_behavior_text)
        self.assertNotIn("suggested_use_now", predicted_behavior_text)
        self.assertNotIn("Social Relationships:", background_identity)

    def test_remember_known_persona_profile_persists_static_traits(self):
        persona = self._build_persona()
        target_persona = self._build_target_persona()

        remembered = remember_known_persona_profile(persona, target_persona, source="unit_test_memory")

        self.assertTrue(remembered)
        cached = persona.scratch.personal_knowledge["persona_profiles"]["Klaus Mueller"]
        self.assertEqual(cached["source"], "unit_test_memory")
        self.assertEqual(cached["innate_traits_text"], "kind, inquisitive, calm")
        self.assertEqual(cached["motive_summary_text"], "主次动机=主satiety, 次mood")

    def test_current_situation_summary_consumes_reflection_thoughts(self):
        persona = self._build_persona()

        refresh_prompt_profile_from_planning(persona, source="unit_test_reflection_summary")

        current_situation = persona.scratch.get_prompt_profile_field("current_situation_text")
        self.assertIn("Recent reflection signals:", current_situation)
        self.assertIn("lunch rush", current_situation)
        self.assertIn("friendship with Klaus Mueller", current_situation)

    def test_llm_current_situation_summary_overrides_heuristic_when_enabled(self):
        persona = self._build_llm_enabled_persona()

        with patch(
            "persona.cognitive_modules.stage1_prompt_compiler.ChatGPT_single_request",
            return_value="Maria Lopez is in a demanding cafe phase and is concentrating on keeping service stable through the lunch rush while leaning on trusted relationships.",
        ):
            refresh_prompt_profile_from_planning(persona, source="unit_test_llm_current")

        current_situation = persona.scratch.get_prompt_profile_field("current_situation_text")
        self.assertIn("demanding cafe phase", current_situation)
        self.assertNotIn("Recent reflection signals:", current_situation)

    def test_llm_long_term_goals_summary_overrides_heuristic_when_enabled(self):
        persona = self._build_llm_enabled_persona()

        with patch(
            "persona.cognitive_modules.stage1_prompt_compiler.ChatGPT_single_request",
            return_value="First I need to stay alive and keep my energy, food, and safety secure. Beyond that, I want to build a steady life by staying useful at the cafe and preserving dependable relationships that make the world feel stable.",
        ):
            refresh_prompt_profile_from_reflection(
                persona,
                planning_thought="For Maria Lopez's planning: I should keep the cafe running smoothly through the lunch rush.",
                memo_thought="Maria Lopez feels she can rely on Klaus Mueller when the cafe gets hectic.",
                source="unit_test_llm_goals",
            )

        long_term_goals = persona.scratch.get_prompt_profile_field("long_term_goals_text")
        self.assertIn("keep my energy, food, and safety secure", long_term_goals)
        self.assertIn("dependable relationships", long_term_goals)


if __name__ == "__main__":
    unittest.main()
