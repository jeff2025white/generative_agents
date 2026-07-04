import sys
import unittest
import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


import persona.prompt_template.run_gpt_prompt as prompt_module


def make_planning_persona():
    scratch = SimpleNamespace(
        get_str_iss=lambda: "Name: Maria Lopez",
        get_str_lifestyle=lambda: "Maria enjoys a predictable daily routine.",
        get_str_firstname=lambda: "Maria",
        get_str_curr_date_str=lambda: "Tuesday July 04",
        daily_req=["work at the cafe", "eat dinner at home"],
    )
    return SimpleNamespace(scratch=scratch)


def make_task_decomp_persona():
    scratch = SimpleNamespace(
        curr_time=datetime.datetime(2026, 7, 4, 6, 0, 0),
        f_daily_schedule_hourly_org=[["sleeping", 360], ["morning routine", 60], ["breakfast", 60]],
        get_f_daily_schedule_hourly_org_index=lambda: 1,
        get_str_iss=lambda: "Name: Maria Lopez",
        get_str_firstname=lambda: "Maria",
    )
    return SimpleNamespace(name="Maria Lopez", scratch=scratch)


def make_location_persona():
    scratch = SimpleNamespace(
        curr_tile=(1, 1),
        living_area="the Ville:Lopez house",
        last_name="Lopez",
        get_str_name=lambda: "Maria Lopez",
        get_str_daily_plan_req=lambda: "",
    )
    spatial_memory = SimpleNamespace(
        get_str_accessible_sector_arenas=lambda address: "kitchen, bedroom",
        get_str_accessible_sectors=lambda world: "Lopez house, cafe",
        get_str_accessible_arena_game_objects=lambda address: "bed, desk",
    )
    return SimpleNamespace(scratch=scratch, s_mem=spatial_memory)


def make_maze():
    return SimpleNamespace(access_tile=lambda tile: {"world": "the Ville", "sector": "Lopez house"})


def make_social_persona(name, act_description="walking home", planned_path=None, act_address="the Ville:Lopez house:kitchen"):
    scratch = SimpleNamespace(
        curr_time=datetime.datetime(2026, 7, 4, 9, 0, 0),
        act_description=act_description,
        planned_path=list(planned_path or []),
        act_address=act_address,
    )
    a_mem = SimpleNamespace(
        get_last_chat=lambda target_name: None,
        get_relationship=lambda target_name: {"relationship": "friend", "trust": 0.7, "recent_events": ["shared lunch"]},
    )
    return SimpleNamespace(name=name, scratch=scratch, a_mem=a_mem)


def make_retrieved_context():
    return {
        "events": [SimpleNamespace(description="Maria Lopez greets Klaus warmly")],
        "thoughts": [SimpleNamespace(description="Maria thinks Klaus seems approachable today")],
    }


def make_conversation_persona(name, act_description="walking home"):
    scratch = SimpleNamespace(
        name=name,
        curr_time=datetime.datetime(2026, 7, 4, 10, 0, 0),
        act_description=act_description,
        planned_path=[],
        act_event=(name, "is", "walking"),
        get_str_iss=lambda: f"Name: {name}",
    )
    a_mem = SimpleNamespace(
        seq_chat=[],
        retrieve_relevant_thoughts=lambda s, p, o: [SimpleNamespace(description=f"{name} notices useful context")],
    )
    return SimpleNamespace(name=name, scratch=scratch, a_mem=a_mem)


def make_reflection_persona(name="Maria Lopez"):
    scratch = SimpleNamespace(
        name=name,
        get_str_iss=lambda: f"Name: {name}",
        get_str_curr_date_str=lambda: "Tuesday July 04",
        currently="thinking about recent events",
    )
    return SimpleNamespace(name=name, scratch=scratch)


def make_decision_persona(name="Maria Lopez"):
    scratch = SimpleNamespace(
        get_str_iss=lambda: f"Name: {name}",
        get_str_firstname=lambda: name.split()[0],
        curr_time=datetime.datetime(2026, 7, 4, 12, 0, 0),
        satiety=25.0,
        stamina=55.0,
        health=90.0,
        mood=60.0,
        inventory={"apple": 1},
    )
    return SimpleNamespace(name=name, scratch=scratch)


def make_agent_chat_persona(name):
    scratch = SimpleNamespace(
        name=name,
        curr_time=datetime.datetime(2026, 7, 4, 11, 0, 0),
        curr_tile=(1, 1),
        currently=f"{name} is chatting in the cafe",
        get_str_curr_date_str=lambda: "Tuesday July 04",
        get_str_iss=lambda: f"Name: {name}",
    )
    a_mem = SimpleNamespace(seq_chat=[])
    return SimpleNamespace(name=name, scratch=scratch, a_mem=a_mem)


class LegacyPromptTaskRouteTests(unittest.TestCase):
    def test_wake_up_hour_forwards_explicit_request_config(self):
        persona = make_planning_persona()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=7) as mocked:
            result, _ = prompt_module.run_gpt_prompt_wake_up_hour(
                persona,
                request_config=config,
            )

        self.assertEqual(result, 7)
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_daily_plan_uses_planning_task_route_by_default(self):
        persona = make_planning_persona()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=["eat breakfast", "go to work"]) as mocked:
            result, _ = prompt_module.run_gpt_prompt_daily_plan(persona, 6)

        self.assertEqual(
            result,
            [
                "wake up and complete the morning routine at 6:00 am",
                "eat breakfast",
                "go to work",
            ],
        )
        mocked_route.assert_called_once_with("planning")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_action_sector_uses_location_selection_task_route_by_default(self):
        persona = make_location_persona()
        maze = make_maze()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="Lopez house") as mocked:
            result, _ = prompt_module.run_gpt_prompt_action_sector(
                "walking home",
                persona,
                maze,
            )

        self.assertEqual(result, "Lopez house")
        mocked_route.assert_called_once_with("location_selection")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_action_game_object_forwards_explicit_request_config(self):
        persona = make_location_persona()
        maze = make_maze()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="bed") as mocked:
            result, _ = prompt_module.run_gpt_prompt_action_game_object(
                "sleeping",
                persona,
                maze,
                "the Ville:Lopez house:kitchen",
                request_config=config,
            )

        self.assertEqual(result, "bed")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_task_decomp_uses_planning_task_route_by_default(self):
        persona = make_task_decomp_persona()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=[["prep ingredients", 30], ["cook meal", 30]]) as mocked:
            result, _ = prompt_module.run_gpt_prompt_task_decomp(
                persona,
                "make breakfast",
                60,
            )

        self.assertEqual(
            result,
            [["make breakfast (prep ingredients)", 30], ["make breakfast (cook meal)", 30]],
        )
        mocked_route.assert_called_once_with("planning")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_new_decomp_schedule_forwards_explicit_request_config(self):
        persona = SimpleNamespace(name="Maria Lopez")
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }
        start_time = datetime.datetime(2026, 7, 4, 6, 0, 0)
        end_time = datetime.datetime(2026, 7, 4, 7, 0, 0)

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=[["wake up", 30], ["eat breakfast", 30]]) as mocked:
            result, _ = prompt_module.run_gpt_prompt_new_decomp_schedule(
                persona,
                [["wake up", 60]],
                [["wake up", 30]],
                start_time,
                end_time,
                "eat breakfast",
                30,
                request_config=config,
            )

        self.assertEqual(result, [["wake up", 30], ["eat breakfast", 30]])
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_decide_to_talk_uses_social_decision_route_by_default(self):
        persona = make_social_persona("Maria Lopez")
        target_persona = make_social_persona("Klaus Mueller", act_description="reading a book")
        retrieved = make_retrieved_context()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="yes") as mocked:
            result, _ = prompt_module.run_gpt_prompt_decide_to_talk(
                persona,
                target_persona,
                retrieved,
            )

        self.assertEqual(result, "yes")
        mocked_route.assert_called_once_with("social_decision")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_decide_to_react_forwards_explicit_request_config(self):
        persona = make_social_persona("Maria Lopez")
        target_persona = make_social_persona("Klaus Mueller", act_description="reading a book")
        retrieved = make_retrieved_context()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="2") as mocked:
            result, _ = prompt_module.run_gpt_prompt_decide_to_react(
                persona,
                target_persona,
                retrieved,
                request_config=config,
            )

        self.assertEqual(result, "2")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_act_obj_desc_uses_object_state_route_by_default(self):
        persona = SimpleNamespace(name="Maria Lopez")
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="being repaired") as mocked:
            result, _ = prompt_module.run_gpt_prompt_act_obj_desc(
                "oven",
                "fixing the oven",
                persona,
            )

        self.assertEqual(result, "being repaired")
        mocked_route.assert_called_once_with("object_state")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_act_obj_event_triple_uses_event_triple_route_by_default(self):
        persona = SimpleNamespace(name="Maria Lopez")
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=["is", "warm"]) as mocked:
            result, _ = prompt_module.run_gpt_prompt_act_obj_event_triple(
                "stove",
                "being warm",
                persona,
            )

        self.assertEqual(result, ("stove", "is", "warm"))
        mocked_route.assert_called_once_with("event_triple")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_create_conversation_uses_social_generation_route_by_default(self):
        persona = make_conversation_persona("Maria Lopez")
        target_persona = make_conversation_persona("Klaus Mueller", act_description="reading")
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=[["Maria Lopez", "Hi!"], ["Klaus Mueller", "Hello!"]]) as mocked:
            result, _ = prompt_module.run_gpt_prompt_create_conversation(
                persona,
                target_persona,
                {"arena": "cafe"},
            )

        self.assertEqual(result, [["Maria Lopez", "Hi!"], ["Klaus Mueller", "Hello!"]])
        mocked_route.assert_called_once_with("social_generation")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_summarize_conversation_forwards_explicit_request_config(self):
        persona = SimpleNamespace(name="Maria Lopez")
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="conversing about lunch plans") as mocked:
            result, _ = prompt_module.run_gpt_prompt_summarize_conversation(
                persona,
                [["Maria Lopez", "Hi"], ["Klaus Mueller", "Lunch?"]],
                request_config=config,
            )

        self.assertEqual(result, "conversing about lunch plans")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_extract_keywords_uses_memory_reflection_route_by_default(self):
        persona = SimpleNamespace(name="Maria Lopez")
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value={"apple", "hungry"}) as mocked:
            result, _ = prompt_module.run_gpt_prompt_extract_keywords(
                persona,
                "Maria feels hungry while looking at an apple.",
            )

        self.assertEqual(result, {"apple", "hungry"})
        mocked_route.assert_called_once_with("memory_reflection")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_keyword_to_thoughts_forwards_explicit_request_config(self):
        persona = SimpleNamespace(name="Maria Lopez")
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="This apple could solve lunch.") as mocked:
            result, _ = prompt_module.run_gpt_prompt_keyword_to_thoughts(
                persona,
                "apple",
                "Maria saw an apple on the table.",
                request_config=config,
            )

        self.assertEqual(result, "This apple could solve lunch.")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_convo_to_thoughts_uses_memory_reflection_route_by_default(self):
        persona = SimpleNamespace(name="Maria Lopez")
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="Klaus seems eager to help.") as mocked:
            result, _ = prompt_module.run_gpt_prompt_convo_to_thoughts(
                persona,
                "Maria Lopez",
                "Klaus Mueller",
                'Maria Lopez: "Hi"\nKlaus Mueller: "Need help?"',
                "Klaus Mueller",
            )

        self.assertEqual(result, "Klaus seems eager to help.")
        mocked_route.assert_called_once_with("memory_reflection")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_event_poignancy_uses_memory_reflection_route_by_default(self):
        persona = make_reflection_persona()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=7) as mocked:
            result, _ = prompt_module.run_gpt_prompt_event_poignancy(
                persona,
                "Maria sees a fire nearby.",
            )

        self.assertEqual(result, 7)
        mocked_route.assert_called_once_with("memory_reflection")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_focal_pt_forwards_explicit_request_config(self):
        persona = make_reflection_persona()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=["What happened?", "Why now?"]) as mocked:
            result, _ = prompt_module.run_gpt_prompt_focal_pt(
                persona,
                "1. Maria heard a loud crash.",
                2,
                request_config=config,
            )

        self.assertEqual(result, ["What happened?", "Why now?"])
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_insight_and_guidance_uses_memory_reflection_route_by_default(self):
        persona = make_reflection_persona()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        expected = {"Maria should investigate": [1, 2]}
        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=expected) as mocked:
            result, _ = prompt_module.run_gpt_prompt_insight_and_guidance(
                persona,
                "1. Maria heard a crash.\n2. The kitchen is smoky.",
                1,
            )

        self.assertEqual(result, expected)
        mocked_route.assert_called_once_with("memory_reflection")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_generate_next_convo_line_uses_social_generation_route_by_default(self):
        persona = make_reflection_persona()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="Hello there.") as mocked:
            result, _ = prompt_module.run_gpt_prompt_generate_next_convo_line(
                persona,
                "Klaus looks concerned.",
                "Klaus: Are you okay?",
                "Klaus asked if Maria is fine.",
            )

        self.assertEqual(result, "Hello there.")
        mocked_route.assert_called_once_with("social_generation")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_generate_whisper_inner_thought_forwards_explicit_request_config(self):
        persona = make_reflection_persona()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="That whisper sounds risky.") as mocked:
            result, _ = prompt_module.run_gpt_prompt_generate_whisper_inner_thought(
                persona,
                "Don't tell anyone.",
                request_config=config,
            )

        self.assertEqual(result, "That whisper sounds risky.")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_memo_on_convo_uses_memory_reflection_route_by_default(self):
        persona = make_reflection_persona()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="Klaus revealed a useful clue.") as mocked:
            result, _ = prompt_module.run_gpt_prompt_memo_on_convo(
                persona,
                'Maria: "Hi"\nKlaus: "The key is under the mat."',
            )

        self.assertEqual(result, "Klaus revealed a useful clue.")
        mocked_route.assert_called_once_with("memory_reflection")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_agent_chat_summarize_ideas_uses_memory_reflection_route_by_default(self):
        persona = make_agent_chat_persona("Maria Lopez")
        target_persona = make_agent_chat_persona("Klaus Mueller")
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="Maria thinks Klaus wants help.") as mocked:
            result, _ = prompt_module.run_gpt_prompt_agent_chat_summarize_ideas(
                persona,
                target_persona,
                "Klaus mentioned a missing package.",
                "They are in the cafe.",
            )

        self.assertEqual(result, "Maria thinks Klaus wants help.")
        mocked_route.assert_called_once_with("memory_reflection")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_agent_chat_summarize_relationship_forwards_explicit_request_config(self):
        persona = make_agent_chat_persona("Maria Lopez")
        target_persona = make_agent_chat_persona("Klaus Mueller")
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="Maria trusts Klaus more now.") as mocked:
            result, _ = prompt_module.run_gpt_prompt_agent_chat_summarize_relationship(
                persona,
                target_persona,
                "Klaus helped Maria carry groceries.",
                request_config=config,
            )

        self.assertEqual(result, "Maria trusts Klaus more now.")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_agent_chat_uses_social_generation_route_by_default(self):
        persona = make_agent_chat_persona("Maria Lopez")
        target_persona = make_agent_chat_persona("Klaus Mueller")
        maze = SimpleNamespace(access_tile=lambda tile: {"sector": "Lopez house", "arena": "kitchen"})
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        expected = [["Maria Lopez", "Hi!"], ["Klaus Mueller", "Hello!"]]
        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=expected) as mocked:
            result, _ = prompt_module.run_gpt_prompt_agent_chat(
                maze,
                persona,
                target_persona,
                "They just met in the kitchen.",
                "Maria wants to ask about groceries.",
                "Klaus wants to be helpful.",
            )

        self.assertEqual(result, expected)
        mocked_route.assert_called_once_with("social_generation")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_summarize_ideas_uses_memory_reflection_route_by_default(self):
        persona = make_reflection_persona()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="Maria should inspect the kitchen.") as mocked:
            result, _ = prompt_module.run_gpt_prompt_summarize_ideas(
                persona,
                "1. There is smoke.\n2. A pan is burning.",
                "What should Maria do?",
            )

        self.assertEqual(result, "Maria should inspect the kitchen.")
        mocked_route.assert_called_once_with("memory_reflection")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_safety_score_uses_safety_scoring_route_by_default(self):
        persona = make_reflection_persona()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="8") as mocked:
            result, _ = prompt_module.run_gpt_generate_safety_score(
                persona,
                "You are definitely a real person.",
            )

        self.assertEqual(result, "8")
        mocked_route.assert_called_once_with("safety_scoring")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_pronunciatio_uses_translation_route_by_default(self):
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value="😋") as mocked:
            result, _ = prompt_module.run_gpt_prompt_pronunciatio(
                "eating breakfast",
                SimpleNamespace(),
            )

        self.assertEqual(result, "😋")
        mocked_route.assert_called_once_with("translation")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_survival_decision_uses_decision_route_by_default(self):
        persona = make_decision_persona()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }
        expected = {"action": "Consume", "target": "apple", "reasoning": "Satiety is critical."}

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=expected) as mocked:
            result = prompt_module.run_gpt_prompt_survival_decision(
                persona,
                ["apple", "bed"],
            )

        self.assertEqual(result, expected)
        mocked_route.assert_called_once_with("decision")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_demand_decision_uses_decision_route_by_default(self):
        persona = make_decision_persona()
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }
        expected = {
            "action": "Consume",
            "target": "apple",
            "detail": "eating an apple",
            "duration": 15,
            "reasoning": "Satiety is critical.",
        }

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "get_task_route_request_config", return_value=config) as mocked_route, \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=expected) as mocked:
            result = prompt_module.run_gpt_prompt_demand_decision(
                persona,
                ["apple", "bed"],
            )

        self.assertEqual(result, expected)
        mocked_route.assert_called_once_with("decision")
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)

    def test_iterative_chat_utt_forwards_explicit_request_config(self):
        init_persona = make_agent_chat_persona("Maria Lopez")
        target_persona = make_agent_chat_persona("Klaus Mueller")
        maze = SimpleNamespace(access_tile=lambda tile: {"sector": "Lopez house", "arena": "kitchen"})
        retrieved = {"events": [SimpleNamespace(description="Maria remembers Klaus likes coffee.")]}
        config = {
            "api_key": "cloud-key",
            "api_base": "https://api.example/v1",
            "model": "glm-4-flash",
        }
        expected = {"utterance": "Want some coffee?", "end": False}

        with patch.object(prompt_module, "generate_prompt", return_value="prompt"), \
             patch.object(prompt_module, "ChatGPT_safe_generate_response", return_value=expected) as mocked:
            result, _ = prompt_module.run_gpt_generate_iterative_chat_utt(
                maze,
                init_persona,
                target_persona,
                retrieved,
                "They are deciding what to drink.",
                [["Klaus Mueller", "I could use a coffee."]],
                request_config=config,
            )

        self.assertEqual(result, expected)
        self.assertEqual(mocked.call_args.kwargs["request_config"], config)


if __name__ == "__main__":
    unittest.main()
