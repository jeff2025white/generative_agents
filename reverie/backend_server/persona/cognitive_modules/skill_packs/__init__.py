from persona.cognitive_modules.skill_packs.gather_skill import GatherSkillPack
from persona.cognitive_modules.skill_packs.consume_skill import ConsumeSkillPack
from persona.cognitive_modules.skill_packs.rest_skill import RestSkillPack
from persona.cognitive_modules.skill_packs.cook_skill import CookSkillPack
from persona.cognitive_modules.skill_packs.coffee_service_skill import CoffeeServiceSkillPack
from persona.cognitive_modules.skill_packs.chat_skill import ChatSkillPack
from persona.cognitive_modules.skill_packs.generic_activity_skill import GenericActivitySkillPack
from persona.cognitive_modules.skill_packs.singing_skill import SingingSkillPack
from persona.cognitive_modules.skill_packs.give_skill import GiveSkillPack
from persona.cognitive_modules.skill_packs.rob_skill import RobSkillPack
from persona.cognitive_modules.skill_packs.request_skill import RequestSkillPack
from persona.cognitive_modules.skill_packs.trade_skill import TradeSkillPack
from persona.cognitive_modules.skill_packs.coordinate_skill import CoordinateSkillPack
from persona.cognitive_modules.skill_packs.pressure_skill import PressureSkillPack
from persona.cognitive_modules.skill_packs.avoid_skill import AvoidSkillPack
from persona.cognitive_modules.skill_packs.social_venue_hangout_skill import SocialVenueHangoutSkillPack
from persona.cognitive_modules.skill_packs.seek_and_chat_skill import SeekAndChatSkillPack
from persona.cognitive_modules.skill_packs.hide_skill import HideSkillPack
from persona.cognitive_modules.skill_packs.collective_worship_skill import CollectiveWorshipSkillPack
from persona.cognitive_modules.skill_packs.occupy_mansion_skill import OccupyMansionSkillPack
from persona.cognitive_modules.skill_packs.smash_fence_skill import SmashFenceSkillPack
from persona.cognitive_modules.skill_packs.long_term_planning_skill import LongTermPlanningSkillPack

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

    # Generic non-survival skills
    "use": GenericActivitySkillPack("use", {"stamina": -3.0, "mood": 1.0}, {}),
    "working": GenericActivitySkillPack("work", {"stamina": -5.0, "mood": -1.0}, {}),
    "work": GenericActivitySkillPack("work", {"stamina": -5.0, "mood": -1.0}, {}),
    "study": GenericActivitySkillPack("study", {"stamina": -4.0, "mood": 1.0}, {}),
    "studying": GenericActivitySkillPack("study", {"stamina": -4.0, "mood": 1.0}, {}),
    "leisure_use": GenericActivitySkillPack("leisure_use", {"stamina": -2.0, "mood": 7.0}, {}),
    "hangout_social_venue": SocialVenueHangoutSkillPack(),
    "hangout": SocialVenueHangoutSkillPack(),
    "daydream": GenericActivitySkillPack("daydream", {"stamina": 2.0, "mood": 5.0}, {}),
    "wander": GenericActivitySkillPack("wander", {"stamina": -1.0, "mood": 1.0}, {}),
    
    # Custom Motive Skills
    "hide": HideSkillPack(),
    "hiding": HideSkillPack(),
    "worship": CollectiveWorshipSkillPack(),
    "worshipping": CollectiveWorshipSkillPack(),
    "pray": CollectiveWorshipSkillPack(),
    "praying": CollectiveWorshipSkillPack(),
    "occupy": OccupyMansionSkillPack(),
    "occupying": OccupyMansionSkillPack(),
    "claim": OccupyMansionSkillPack(),
    "claiming": OccupyMansionSkillPack(),
    "smash": SmashFenceSkillPack(),
    "smashing": SmashFenceSkillPack(),
    "bashing": SmashFenceSkillPack(),
    "plan": LongTermPlanningSkillPack(),
    "planning": LongTermPlanningSkillPack(),
    "micro-planning": LongTermPlanningSkillPack(),
    
    # Pluggable Chat Skill Pack mapping
    "chat with": ChatSkillPack(),
    "seek_and_chat": SeekAndChatSkillPack(),
    "seek chat": SeekAndChatSkillPack(),
    "chat": ChatSkillPack(),
    "talk": ChatSkillPack(),
    "whisper": ChatSkillPack(),
    "monologue": ChatSkillPack(),
    "communicate": ChatSkillPack(),
    "creator_comm": ChatSkillPack(),

    # NPC-to-NPC resource exchange skills
    "request": RequestSkillPack(),
    "requesting": RequestSkillPack(),
    "ask": RequestSkillPack(),
    "asking": RequestSkillPack(),
    "seek": RequestSkillPack(),
    "trade": TradeSkillPack(),
    "trading": TradeSkillPack(),
    "exchange": TradeSkillPack(),
    "exchanging": TradeSkillPack(),
    "barter": TradeSkillPack(),
    "bartering": TradeSkillPack(),
    "coordinate": CoordinateSkillPack(),
    "coordinating": CoordinateSkillPack(),
    "cooperate": CoordinateSkillPack(),
    "cooperating": CoordinateSkillPack(),
    "align": CoordinateSkillPack(),
    "team up": CoordinateSkillPack(),
    "pressure": PressureSkillPack(),
    "pressuring": PressureSkillPack(),
    "push": PressureSkillPack(),
    "pushing": PressureSkillPack(),
    "corner": PressureSkillPack(),
    "demand": PressureSkillPack(),
    "avoid": AvoidSkillPack(),
    "avoiding": AvoidSkillPack(),
    "bypass": AvoidSkillPack(),
    "disengage": AvoidSkillPack(),
    "leave": AvoidSkillPack(),
    "give": GiveSkillPack(),
    "giving": GiveSkillPack(),
    "gift": GiveSkillPack(),
    "donate": GiveSkillPack(),
    "share": GiveSkillPack(),
    "rob": RobSkillPack(),
    "robbing": RobSkillPack(),
    "steal": RobSkillPack(),
    "stealing": RobSkillPack(),
    "loot": RobSkillPack(),
    "mug": RobSkillPack(),
}
