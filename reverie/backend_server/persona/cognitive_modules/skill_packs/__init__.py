from persona.cognitive_modules.skill_packs.gather_skill import GatherSkillPack
from persona.cognitive_modules.skill_packs.consume_skill import ConsumeSkillPack
from persona.cognitive_modules.skill_packs.rest_skill import RestSkillPack
from persona.cognitive_modules.skill_packs.cook_skill import CookSkillPack
from persona.cognitive_modules.skill_packs.coffee_service_skill import CoffeeServiceSkillPack
from persona.cognitive_modules.skill_packs.chat_skill import ChatSkillPack
from persona.cognitive_modules.skill_packs.singing_skill import SingingSkillPack

SKILL_REGISTRY = {
    "gather": GatherSkillPack(),
    "consume": ConsumeSkillPack(),
    "rest": RestSkillPack(),
    "cook": CookSkillPack(),
    "brew": CoffeeServiceSkillPack(),
    "serve": CoffeeServiceSkillPack(),
    "drink": CoffeeServiceSkillPack(),
    
    # Singing skill registration
    "sing": SingingSkillPack(),
    "singing": SingingSkillPack(),
    
    # Pluggable Chat Skill Pack mapping
    "chat with": ChatSkillPack(),
    "chat": ChatSkillPack(),
    "talk": ChatSkillPack(),
    "whisper": ChatSkillPack(),
    "monologue": ChatSkillPack(),
    "communicate": ChatSkillPack(),
    "creator_comm": ChatSkillPack()
}
