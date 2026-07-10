import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from persona.cognitive_modules.motive_selector import select_motives
from persona.cognitive_modules.motive_selector import (
    apply_passive_motive_decay,
    apply_skill_motive_effects,
    build_default_motive_attributes,
    build_persona_motive_attributes,
    generate_innate_traits_from_motives,
    summarize_motive_drivers,
    sync_core_motive_values,
)


class MotiveSelectorTests(unittest.TestCase):
    def test_hunger_and_fatigue_become_primary_secondary(self):
        result = select_motives(
            {
                "satiety": {
                    "current_value": 22.0,
                    "initial_value": 60.0,
                    "safe_threshold": 50.0,
                    "critical_threshold": 20.0,
                },
                "stamina": {
                    "current_value": 35.0,
                    "initial_value": 70.0,
                    "safe_threshold": 45.0,
                    "critical_threshold": 20.0,
                },
                "mood": {
                    "current_value": 65.0,
                    "initial_value": 60.0,
                    "safe_threshold": 50.0,
                    "critical_threshold": 30.0,
                },
            }
        )

        self.assertEqual(result["dominant_motive"], "satiety")
        self.assertEqual(result["secondary_motive"], "stamina")
        self.assertEqual(
            result["motive_sentence"],
            "我有些饿了，我想尽快吃点东西；我有点累了，最好尽快休息一下。",
        )

    def test_critical_mood_triggers_guard_motive(self):
        result = select_motives(
            {
                "mood": {
                    "current_value": 28.0,
                    "initial_value": 60.0,
                    "safe_threshold": 50.0,
                    "critical_threshold": 30.0,
                },
                "status": {
                    "current_value": 42.0,
                    "initial_value": 55.0,
                    "safe_threshold": 45.0,
                    "critical_threshold": 25.0,
                },
                "belonging": {
                    "current_value": 62.0,
                    "initial_value": 60.0,
                    "safe_threshold": 50.0,
                    "critical_threshold": 30.0,
                },
            }
        )

        self.assertEqual(result["dominant_motive"], "mood")
        self.assertEqual(result["secondary_motive"], "status")
        self.assertEqual(result["guard_motive"], "mood")
        self.assertEqual(
            result["motive_sentence"],
            "我太伤心了，我必须立刻提升情绪；我有些在意面子，想尽快证明一下自己。",
        )

    def test_custom_text_override_is_respected(self):
        result = select_motives(
            {
                "status": {
                    "current_value": 20.0,
                    "initial_value": 60.0,
                    "safe_threshold": 50.0,
                    "critical_threshold": 25.0,
                    "desire_text": "我想要重新赢得别人的注意",
                    "guard_text": "我颜面尽失，我必须立刻成为焦点",
                },
                "exploration": {
                    "current_value": 48.0,
                    "initial_value": 60.0,
                    "safe_threshold": 50.0,
                    "critical_threshold": 30.0,
                },
            }
        )

        self.assertEqual(result["dominant_motive"], "status")
        self.assertEqual(result["guard_motive"], "status")
        self.assertIn("我颜面尽失，我必须立刻成为焦点", result["motive_sentence"])

    def test_empty_input_returns_empty_result(self):
        result = select_motives({})

        self.assertIsNone(result["dominant_motive"])
        self.assertEqual(result["motive_sentence"], "")

    def test_passive_decay_is_npc_specific(self):
        motive_attributes = build_default_motive_attributes(
            overrides={
                "belonging": {"current_value": 60.0, "decay_per_step": 0.8},
                "status": {"current_value": 60.0, "decay_per_step": 0.1},
            }
        )

        updated, applied = apply_passive_motive_decay(motive_attributes, skip_motives={"satiety", "stamina", "health", "mood"})

        self.assertEqual(applied["belonging"], -0.8)
        self.assertEqual(applied["status"], -0.1)
        self.assertEqual(updated["belonging"]["current_value"], 59.2)
        self.assertEqual(updated["status"]["current_value"], 59.9)

    def test_skill_settlement_uses_npc_specific_bonuses(self):
        motive_attributes = build_default_motive_attributes(
            overrides={
                "mood": {
                    "current_value": 45.0,
                    "skill_flat_modifiers": {"chat": 4.0},
                    "skill_scale_modifiers": {"chat": 1.5},
                }
            }
        )

        updated, applied = apply_skill_motive_effects(
            motive_attributes,
            skill_id="chat",
            motive_effects={"mood": 6.0},
        )

        self.assertEqual(applied["mood"], 15.0)
        self.assertEqual(updated["mood"]["current_value"], 60.0)

    def test_core_state_sync_overwrites_core_motive_values(self):
        motive_attributes = build_default_motive_attributes(
            overrides={
                "satiety": {"current_value": 80.0},
                "mood": {"current_value": 75.0},
            }
        )

        updated = sync_core_motive_values(
            motive_attributes,
            satiety=30.0,
            stamina=55.0,
            health=90.0,
            mood=40.0,
        )

        self.assertEqual(updated["satiety"]["current_value"], 30.0)
        self.assertEqual(updated["mood"]["current_value"], 40.0)

    def test_exploration_growth_alias_maps_to_meaning(self):
        motive_attributes = build_default_motive_attributes(
            overrides={
                "meaning": {
                    "current_value": 50.0,
                }
            }
        )

        updated, applied = apply_skill_motive_effects(
            motive_attributes,
            skill_id="study",
            motive_effects={"exploration_growth": 8.0},
        )

        self.assertEqual(applied["meaning"], 8.0)
        self.assertEqual(updated["meaning"]["current_value"], 58.0)

    def test_motive_summary_includes_score_lookup(self):
        summary = summarize_motive_drivers(
            {
                "satiety": {
                    "current_value": 18.0,
                    "initial_value": 60.0,
                    "safe_threshold": 50.0,
                    "critical_threshold": 25.0,
                },
                "mood": {
                    "current_value": 22.0,
                    "initial_value": 60.0,
                    "safe_threshold": 50.0,
                    "critical_threshold": 30.0,
                },
            }
        )

        self.assertEqual(summary["guard_motive"], "satiety")
        self.assertIn("satiety", summary["scores_by_motive"])
        self.assertIn("mood", summary["scores_by_motive"])

    def test_motive_summary_preserves_dominant_and_scores(self):
        summary = summarize_motive_drivers(
            {
                "satiety": {
                    "current_value": 72.0,
                    "initial_value": 60.0,
                    "safe_threshold": 50.0,
                    "critical_threshold": 25.0,
                },
                "stamina": {
                    "current_value": 74.0,
                    "initial_value": 75.0,
                    "safe_threshold": 45.0,
                    "critical_threshold": 20.0,
                },
                "health": {
                    "current_value": 84.0,
                    "initial_value": 85.0,
                    "safe_threshold": 55.0,
                    "critical_threshold": 25.0,
                },
                "mood": {
                    "current_value": 34.0,
                    "initial_value": 60.0,
                    "safe_threshold": 50.0,
                    "critical_threshold": 30.0,
                },
            }
        )

        self.assertEqual(summary["dominant_motive"], "mood")
        self.assertIn("mood", summary["scores_by_motive"])

    def test_stable_satiety_does_not_emit_hunger_sentence(self):
        summary = summarize_motive_drivers(
            {
                "satiety": {
                    "current_value": 91.4,
                    "initial_value": 62.0,
                    "safe_threshold": 50.0,
                    "critical_threshold": 25.0,
                    "decay_per_step": 0.08,
                },
                "stamina": {
                    "current_value": 94.4,
                    "initial_value": 100.0,
                    "safe_threshold": 45.0,
                    "critical_threshold": 20.0,
                    "decay_per_step": 0.04,
                },
                "mood": {
                    "current_value": 52.7,
                    "initial_value": 60.0,
                    "safe_threshold": 50.0,
                    "critical_threshold": 30.0,
                    "decay_per_step": 0.03,
                },
            }
        )

        self.assertEqual(summary["dominant_motive"], "satiety")
        self.assertEqual(summary["dominant_urgency_band"], "stable")
        self.assertEqual(summary["dominant_strength"], "weak")
        self.assertFalse(summary["has_urgent_motive"])
        self.assertEqual(summary["motive_sentence"], "")
        self.assertIsNone(summary["secondary_motive"])

    def test_named_persona_profiles_produce_distinct_motive_parameters(self):
        maria = build_persona_motive_attributes("Maria Lopez")
        isabella = build_persona_motive_attributes("Isabella Rodriguez")
        klaus = build_persona_motive_attributes("Klaus Mueller")

        self.assertNotEqual(maria["autonomy"]["initial_value"], isabella["autonomy"]["initial_value"])
        self.assertNotEqual(isabella["belonging"]["priority_weight"], klaus["belonging"]["priority_weight"])
        self.assertNotEqual(klaus["meaning"]["initial_value"], maria["meaning"]["initial_value"])
        self.assertEqual(maria["competence"]["skill_flat_modifiers"]["study"], 4.0)
        self.assertEqual(isabella["belonging"]["skill_flat_modifiers"]["chat with"], 5.0)
        self.assertEqual(klaus["meaning"]["skill_flat_modifiers"]["study"], 5.0)

    @patch(
        "persona.cognitive_modules.motive_selector.ChatGPT_safe_generate_response",
        return_value="friendly, outgoing, hospitable",
    )
    def test_generate_innate_traits_from_motives_prefers_llm_phrase(self, _mock_llm):
        scratch = type(
            "ScratchStub",
            (),
            {
                "name": "Maria Lopez",
                "lifestyle": "cafe host with a regular service routine",
                "learned": "good at serving customers",
                "currently": "opening the cafe",
                "innate": "legacy trait text",
                "satiety": 58.0,
                "stamina": 70.0,
                "health": 90.0,
                "mood": 66.0,
                "motive_attributes": build_persona_motive_attributes("Maria Lopez"),
                "get_motive_attributes_snapshot": lambda self=None: build_persona_motive_attributes("Maria Lopez"),
            },
        )()

        result = generate_innate_traits_from_motives(scratch, force_llm=True)

        self.assertEqual(result, "friendly, outgoing, hospitable")


if __name__ == "__main__":
    unittest.main()
