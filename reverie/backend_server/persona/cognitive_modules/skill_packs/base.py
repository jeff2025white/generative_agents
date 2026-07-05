from persona.prompt_template.gpt_structure import ChatGPT_safe_generate_response

class BaseSkillPack:
    def __init__(self):
        self.name = ""          # Unique identifier for the skill (maps to the LLM's chosen action)
        self.associated_xp = "" # Associated skill tree node (e.g. "gathering", "cooking")

    def finish_success(self, persona, *, action_command=None, action_event=None, action_description=None, action_address=None):
        """
        Record a successful completion and release the active execution state.
        Skill implementations should prefer this over manually mutating scratch fields.
        """
        persona.scratch.mark_action_completed(
            action_command=action_command or persona.scratch.act_command,
            action_event=action_event or persona.scratch.act_event,
            action_description=action_description or persona.scratch.act_description,
            action_address=action_address or persona.scratch.act_address,
        )
        if hasattr(persona.scratch, "complete_execution"):
            persona.scratch.complete_execution()
        else:
            persona.scratch.clear_current_action()

    def finish_failure(self, persona, reason, payload=None):
        """
        Release the active execution state as a failure.
        """
        if hasattr(persona.scratch, "fail_execution"):
            persona.scratch.fail_execution(reason, payload=payload)
        else:
            persona.scratch.clear_current_action()

    def finish_interrupted(self, persona, reason, payload=None):
        """
        Release the active execution state as an interruption.
        """
        if hasattr(persona.scratch, "interrupt_execution"):
            persona.scratch.interrupt_execution(reason, payload=payload)
        else:
            persona.scratch.clear_current_action()

    def run_skill_llm_request(
        self,
        prompt,
        example_output,
        special_instruction,
        fail_safe_response,
        repeat=3,
        func_validate=None,
        func_clean_up=None,
        verbose=False,
        prompt_kind="generic",
        metadata=None,
        request_config=None,
        skip_cache=False,
    ):
        """
        Unified LLM request interface for all skill packs. 
        Ensures consistent API calling pattern and simplifies prompt management.
        """
        try:
            return ChatGPT_safe_generate_response(
                prompt, example_output, special_instruction,
                repeat=repeat, fail_safe_response=fail_safe_response,
                func_validate=func_validate, func_clean_up=func_clean_up,
                verbose=verbose,
                prompt_kind=prompt_kind,
                metadata=metadata,
                request_config=request_config,
                skip_cache=skip_cache,
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
        Implementations should terminate via finish_success(), finish_failure(), or finish_interrupted()
        instead of manually clearing scratch action fields.
        """
        raise NotImplementedError
