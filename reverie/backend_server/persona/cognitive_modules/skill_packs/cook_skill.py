import json
from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.prompt_template.gpt_structure import ChatGPT_safe_generate_response

class CookSkillPack(BaseSkillPack):
    def __init__(self):
        super().__init__()
        self.name = "cook"
        self.associated_xp = "cooking"

    def can_execute(self, persona, target, maze) -> bool:
        # Prerequisite: Must be near stove/microwave and have at least one ingredient
        return len(persona.scratch.inventory) > 0 and persona.s_mem.find_nearest_object(target) is not None

    def get_target_tiles(self, persona, target, maze) -> list:
        address = persona.s_mem.find_nearest_object(target)
        if address and address in maze.address_tiles:
            return list(maze.address_tiles[address])
        return []

    def cognitive_decision(self, persona, target, maze, personas) -> dict:
        ingredients = [k for k, v in persona.scratch.inventory.items() if v > 0]
        if not ingredients:
            return {"dish": "raw apple", "monologue": "I will just eat a raw apple."}

        # Mini prompt for recipe selection
        prompt = (
            f"You are {persona.name}. You are at the stove to cook.\n"
            f"Your current ingredients in inventory: {ingredients}.\n"
            f"Decide on one cooked dish to make and generate a short monologue about your cooking process."
        )
        example_output = '{"dish": "cooked apple", "monologue": "Let\'s bake these apples with some sugar."}'
        special_instruction = "Select a dish using the ingredients. Respond only in JSON."
        
        try:
            response = ChatGPT_safe_generate_response(
                prompt, example_output, special_instruction,
                repeat=2, fail_safe_response={"dish": "cooked apple", "monologue": "Cooking some apples."},
                verbose=False
            )
            # Handle list/tuple response wrapped in ChatGPT_safe_generate_response returns
            if isinstance(response, list) or isinstance(response, tuple):
                response = response[0]
            if isinstance(response, str):
                cleaned = response.strip()
                start = cleaned.find("{")
                end = cleaned.rfind("}") + 1
                if start != -1 and end != -1:
                    cleaned = cleaned[start:end]
                response = json.loads(cleaned)
            return response
        except Exception as e:
            print(f"Error in CookSkillPack cognitive decision: {e}")
            return {"dish": "cooked apple", "monologue": "Cooking some apples."}

    def on_arrive(self, persona, target, maze, personas):
        # 1. Cognitive decision
        decision = self.cognitive_decision(persona, target, maze, personas)
        dish = decision.get("dish", "cooked apple")
        monologue = decision.get("monologue", "Cooking food.")

        # 2. Consumption and production
        ingredients = [k for k, v in persona.scratch.inventory.items() if v > 0]
        if ingredients:
            raw_item = ingredients[0]
            persona.scratch.inventory[raw_item] -= 1
        persona.scratch.inventory[dish] = persona.scratch.inventory.get(dish, 0) + 1

        # 3. Settlement
        persona.scratch.skills[self.associated_xp]["xp"] += 15
        persona.scratch.act_pronunciatio = "🍳"
        print(f"=== [大模型辅助技能结算] {persona.name} 烹饪了 {dish}! 独白: {monologue} ===")
