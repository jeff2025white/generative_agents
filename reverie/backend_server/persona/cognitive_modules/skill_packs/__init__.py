from persona.cognitive_modules.skill_packs.gather_skill import GatherSkillPack
from persona.cognitive_modules.skill_packs.consume_skill import ConsumeSkillPack
from persona.cognitive_modules.skill_packs.rest_skill import RestSkillPack
from persona.cognitive_modules.skill_packs.cook_skill import CookSkillPack
from persona.cognitive_modules.skill_packs.coffee_service_skill import CoffeeServiceSkillPack
from persona.cognitive_modules.skill_packs.chat_skill import ChatSkillPack
from persona.cognitive_modules.skill_packs.singing_skill import SingingSkillPack

SKILL_REGISTRY = {
    # Consume Skill
    "consume": ConsumeSkillPack(),
    "consuming": ConsumeSkillPack(),
    "eat": ConsumeSkillPack(),
    "eating": ConsumeSkillPack(),
    "have": ConsumeSkillPack(),
    "having": ConsumeSkillPack(),
    "snack": ConsumeSkillPack(),
    "snacking": ConsumeSkillPack(),
    "drink": ConsumeSkillPack(),
    "drinking": ConsumeSkillPack(),
    
    # Gather Skill
    "gather": GatherSkillPack(),
    "gathering": GatherSkillPack(),
    "get": GatherSkillPack(),
    "getting": GatherSkillPack(),
    "take": GatherSkillPack(),
    "taking": GatherSkillPack(),
    "harvest": GatherSkillPack(),
    "harvesting": GatherSkillPack(),
    "prepare": GatherSkillPack(),
    "preparing": GatherSkillPack(),
    
    # Rest Skill
    "rest": RestSkillPack(),
    "resting": RestSkillPack(),
    "sleep": RestSkillPack(),
    "sleeping": RestSkillPack(),
    "nap": RestSkillPack(),
    "napping": RestSkillPack(),
    "snooze": RestSkillPack(),
    "snoozing": RestSkillPack(),
    "idle": RestSkillPack(),
    "idling": RestSkillPack(),
    "relax": RestSkillPack(),
    "relaxing": RestSkillPack(),
    "lie down": RestSkillPack(),
    "lying down": RestSkillPack(),
    
    # Other Skills
    "cook": CookSkillPack(),
    "brew": CoffeeServiceSkillPack(),
    "serve": CoffeeServiceSkillPack(),
    
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
