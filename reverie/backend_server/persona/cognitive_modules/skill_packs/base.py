from persona.prompt_template.gpt_structure import ChatGPT_safe_generate_response

class BaseSkillPack:
    def __init__(self):
        self.name = ""          # Unique identifier for the skill (maps to the LLM's chosen action)
        self.associated_xp = "" # Associated skill tree node (e.g. "gathering", "cooking")

    def run_skill_llm_request(self, prompt, example_output, special_instruction, fail_safe_response, repeat=3, func_validate=None, func_clean_up=None, verbose=False):
        """
        Unified LLM request interface for all skill packs. 
        Ensures consistent API calling pattern and simplifies prompt management.
        """
        try:
            return ChatGPT_safe_generate_response(
                prompt, example_output, special_instruction,
                repeat=repeat, fail_safe_response=fail_safe_response,
                func_validate=func_validate, func_clean_up=func_clean_up,
                verbose=verbose
            )
        except Exception as e:
            print(f"Error in run_skill_llm_request for skill '{self.name}': {e}")
            return fail_safe_response

    def can_execute(self, persona, target, maze) -> bool:
        """
        Physical prerequisite check. Returns True if physical constraints are met, False otherwise.
        """
        raise NotImplementedError

    def cognitive_decision(self, persona, target, maze, personas) -> dict:
        """
        Optional mini-LLM cognitive decision helper. Call this when the skill requires fine-grained 
        subjective choices (like choosing which recipe to cook, or dialogue bubble options).
        """
        return {}

    def get_target_tiles(self, persona, target, maze) -> list:
        """
        Spatial query to locate valid coordinate tiles for executing this action.
        """
        raise NotImplementedError

    def on_arrive(self, persona, target, maze, personas):
        """
        Physical outcome settlement upon arrival (metabolism updates, inventory changes, XP awards, memories).
        """
        raise NotImplementedError
