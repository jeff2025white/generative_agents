def _normalize_text(raw_text):
    if not raw_text:
        return ""
    return str(raw_text).strip().lower()


def _contains_any(text, keywords):
    return any(keyword in text for keyword in keywords)


def normalize_action_target(target):
    normalized = _normalize_text(target)
    if ":" in normalized:
        normalized = normalized.split(":")[-1]
    normalized = normalized.replace("_", " ")
    return " ".join(normalized.split())


def normalize_skill_id(raw_action, target=None, detail=None):
    if not raw_action:
        return None

    action = _normalize_text(raw_action)
    target_text = _normalize_text(target)
    detail_text = _normalize_text(detail)
    context_text = " ".join([action, target_text, detail_text]).strip()
    if action in {"idle", "idling"} and _contains_any(context_text, ["daydream", "people-watch", "people watch", "zone out", "stare into space", "spacing out"]):
        return "daydream"
    alias_map = {
        "consume": "consume",
        "consuming": "consume",
        "eat": "consume",
        "eating": "consume",
        "drink": "consume",
        "drinking": "consume",
        "have": "consume",
        "having": "consume",
        "snack": "consume",
        "snacking": "consume",
        "gather": "gather",
        "gathering": "gather",
        "get": "gather",
        "getting": "gather",
        "take": "gather",
        "taking": "gather",
        "retrieve": "gather",
        "retrieving": "gather",
        "search": "gather",
        "searching": "gather",
        "open": "gather",
        "opening": "gather",
        "harvest": "gather",
        "harvesting": "gather",
        "prepare": "gather",
        "preparing": "gather",
        "rest": "rest",
        "resting": "rest",
        "sleep": "rest",
        "sleeping": "rest",
        "nap": "rest",
        "napping": "rest",
        "idle": "idle",
        "idling": "idle",
        "daydream": "daydream",
        "daydreaming": "daydream",
        "zone out": "daydream",
        "zoning out": "daydream",
        "relax": "rest",
        "relaxing": "rest",
        "wander": "wander",
        "wandering": "wander",
        "stroll": "wander",
        "strolling": "wander",
        "meander": "wander",
        "meandering": "wander",
        "chat with": "chat with",
        "seek_and_chat": "seek_and_chat",
        "seek chat": "seek_and_chat",
        "chat": "chat with",
        "talk": "chat with",
        "socialize": "chat with",
        "socializing": "chat with",
        "communicate": "chat with",
        "hangout_social_venue": "hangout_social_venue",
        "hangout": "hangout_social_venue",
        "loiter": "hangout_social_venue",
        "linger": "hangout_social_venue",
        "give": "give",
        "giving": "give",
        "gift": "give",
        "donate": "give",
        "donating": "give",
        "share": "give",
        "sharing": "give",
        "rob": "rob",
        "robbing": "rob",
        "steal": "rob",
        "stealing": "rob",
        "loot": "rob",
        "looting": "rob",
        "mug": "rob",
        "mugging": "rob",
        "creator_comm": "creator_comm",
        "execute": "use",
        "recreate": "leisure_use",
        "recreation": "leisure_use",
        "leisure": "leisure_use",
        "play": "leisure_use",
        "playing": "leisure_use",
        "watch": "leisure_use",
        "watching": "leisure_use",
        "listen": "leisure_use",
        "listening": "leisure_use",
        "paint": "leisure_use",
        "painting": "leisure_use",
        "draw": "leisure_use",
        "drawing": "leisure_use",
        "use": "use",
        "using": "use",
        "exercise": "use",
        "exercising": "use",
        "work": "work",
        "working": "work",
        "teach": "work",
        "teaching": "work",
        "organize": "work",
        "organizing": "work",
        "study": "study",
        "studying": "study",
        "read": "study",
        "reading": "study",
        "write": "study",
        "writing": "study",
        "research": "study",
        "researching": "study",
    }

    if action not in {"recreate", "recreation", "leisure", "play", "playing", "use", "using", "work", "working"}:
        return alias_map.get(action)

    if _contains_any(context_text, ["wander", "wandering", "stroll", "strolling", "meander", "meandering"]) and _contains_any(context_text, ["park", "garden", "plaza", "courtyard", "green"]):
        return "wander"
    if _contains_any(context_text, ["daydream", "people-watch", "people watch", "zone out", "stare into space", "spacing out"]):
        return "daydream"
    if _contains_any(context_text, ["chat with", "chatting with", "conversation with", "talking with", "talk to", "gossip with", "socializing with"]):
        return "chat with"
    if "singing" in context_text or _contains_any(context_text, ["piano", "song", "music", "karaoke", "melody"]):
        return "sing"
    if _contains_any(context_text, ["bed", "sofa", "couch", "bench", "chair", "nap", "sleep", "rest", "lying down", "lie down"]):
        return "rest"
    if _contains_any(context_text, ["computer", "bookshelf", "blackboard", "classroom", "study", "research", "read", "writing", "write", "homework", "library table", "library desk", "desk study"]):
        return "study"
    if _contains_any(context_text, ["counter", "register", "coffee maker", "office", "serve", "cashier", "fulfill daily role", "job", "shift", "duty"]):
        return "work"
    if _contains_any(context_text, ["exercise machine", "fitness machine", "game console", "tv", "television", "pool table", "easel", "workout machine", "equipment"]):
        return "use" if action in {"use", "using", "work", "working"} else "leisure_use"

    return alias_map.get(action)


def infer_intent_family(skill_id=None, target=None, detail=None):
    normalized_skill = normalize_skill_id(skill_id, target=target, detail=detail)
    normalized_target = normalize_action_target(target)
    detail_text = _normalize_text(detail)
    context_text = " ".join([normalized_target, detail_text]).strip()
    food_keywords = [
        "apple",
        "food",
        "meal",
        "snack",
        "crackers",
        "refrigerator",
        "fridge",
        "stove",
        "toaster",
        "microwave",
        "counter",
        "cabinet",
        "apple tree",
        "cafe",
    ]

    if normalized_skill == "rest":
        return "restore_stamina"
    if normalized_skill == "idle":
        return "idle"
    if normalized_skill in {"daydream", "wander"}:
        return "leisure"
    if normalized_skill in {"consume", "gather"}:
        if _contains_any(context_text, food_keywords):
            return "restore_satiety"
        return "acquire_resource"
    if normalized_skill in {"chat with", "seek_and_chat", "creator_comm"}:
        return "communication"
    if normalized_skill == "give":
        return "communication"
    if normalized_skill == "rob":
        return "acquire_resource"
    if normalized_skill == "study":
        return "study"
    if normalized_skill == "work":
        return "work"
    if normalized_skill in {"use", "leisure_use", "hangout_social_venue", "sing", "daydream", "wander"}:
        return "leisure"
    return normalized_skill or "unknown"


def build_decision_signature(action_command=None, action_event=None, action_description=None, action_address=None):
    command = action_command or {}
    raw_target = command.get("target")
    if raw_target in {None, "", "none"} and action_event and len(action_event) >= 3:
        raw_target = action_event[2]
    if raw_target in {None, "", "none"} and action_address:
        raw_target = action_address

    detail = command.get("detail") if isinstance(command, dict) else None
    if not detail:
        detail = action_description

    raw_skill = None
    if isinstance(command, dict):
        raw_skill = command.get("skill_id") or command.get("raw_action")
    if not raw_skill and action_event and len(action_event) >= 2:
        raw_skill = action_event[1]

    normalized_target = normalize_action_target(raw_target)
    normalized_skill = normalize_skill_id(raw_skill, target=normalized_target, detail=detail)
    return {
        "skill_id": normalized_skill,
        "target": normalized_target,
        "intent_family": infer_intent_family(normalized_skill, target=normalized_target, detail=detail),
    }


def build_action_command(skill_id=None, target=None, source="unknown", raw_action=None, detail=None):
    normalized_skill_id = normalize_skill_id(skill_id or raw_action, target=target, detail=detail)
    return {
        "skill_id": normalized_skill_id,
        "target": target,
        "source": source,
        "raw_action": raw_action if raw_action is not None else skill_id,
        "detail": detail,
    }


def infer_action_command_from_event(action_event, source="act_event", detail=None):
    if not action_event or len(action_event) < 3:
        return build_action_command(None, None, source=source, raw_action=None, detail=detail)
    raw_action = action_event[1]
    target = action_event[2]
    return build_action_command(None, target, source=source, raw_action=raw_action, detail=detail)
