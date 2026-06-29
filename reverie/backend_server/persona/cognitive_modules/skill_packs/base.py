class BaseSkillPack:
    def __init__(self):
        self.name = ""          # Unique identifier for the skill (maps to the LLM's chosen action)
        self.associated_xp = "" # Associated skill tree node (e.g. "gathering", "cooking")

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
