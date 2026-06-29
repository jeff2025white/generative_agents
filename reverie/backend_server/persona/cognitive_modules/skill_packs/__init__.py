from persona.cognitive_modules.skill_packs.gather_skill import GatherSkillPack
from persona.cognitive_modules.skill_packs.consume_skill import ConsumeSkillPack
from persona.cognitive_modules.skill_packs.rest_skill import RestSkillPack
from persona.cognitive_modules.skill_packs.cook_skill import CookSkillPack
from persona.cognitive_modules.skill_packs.coffee_service_skill import CoffeeServiceSkillPack
from persona.cognitive_modules.skill_packs.chat_skill import ChatSkillPack

SKILL_REGISTRY = {
    "gather": GatherSkillPack(),
    "consume": ConsumeSkillPack(),
    "rest": RestSkillPack(),
    "cook": CookSkillPack(),
    "brew": CoffeeServiceSkillPack(),
    "serve": CoffeeServiceSkillPack(),
    "drink": CoffeeServiceSkillPack(),
    
    # Pluggable Chat Skill Pack mapping
    "chat with": ChatSkillPack(),
    "chat": ChatSkillPack(),
    "talk": ChatSkillPack(),
    "whisper": ChatSkillPack(),
    "monologue": ChatSkillPack(),
    "communicate": ChatSkillPack(),
    "creator_comm": ChatSkillPack()
}
