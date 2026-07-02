"""Deterministic address resolution for common non-survival targets."""


KNOWN_OBJECT_HINTS = {
    "refrigerator": ["refrigerator", "fridge", "kitchen fridge"],
    "piano": ["piano"],
    "library table": ["library table", "library desk"],
    "game console": ["game console", "console"],
    "computer": ["computer desk", "computer", "laptop"],
    "desk": ["desk"],
    "pool table": ["pool table"],
    "behind the cafe counter": ["behind the cafe counter", "cafe counter"],
    "cafe customer seating": ["cafe customer seating", "customer seating"],
    "blackboard": ["blackboard"],
    "bookshelf": ["bookshelf"],
    "tv": ["tv", "television"],
    "sofa": ["sofa", "couch"],
    "bed": ["bed"],
}


KNOWN_ARENA_RULES = [
    {
        "triggers": ["hobbs cafe", "cafe"],
        "preferred_keywords": ["cafe"],
        "excluded_keywords": [],
    },
    {
        "triggers": ["library", "library table", "bookshelf", "blackboard"],
        "preferred_keywords": ["library", "classroom"],
        "excluded_keywords": [],
    },
    {
        "triggers": ["common room"],
        "preferred_keywords": ["common room"],
        "excluded_keywords": [],
    },
    {
        "triggers": ["fitness machine", "exercise machine", "workout machine", "gym"],
        "preferred_keywords": ["gym", "fitness", "exercise", "recreation"],
        "excluded_keywords": ["cafe"],
    },
    {
        "triggers": ["piano", "music"],
        "preferred_keywords": ["piano", "music", "recreation", "common room"],
        "excluded_keywords": [],
    },
]


def _normalize_text(value):
    return str(value or "").strip().lower()


def _combined_text(*values):
    return " ".join(_normalize_text(value) for value in values if value).strip()


def _iter_arena_addresses(maze):
    for address in maze.address_tiles:
        if len(address.split(":")) == 3:
            yield address


def _find_matching_arena_address(maze, preferred_keywords, excluded_keywords=None):
    excluded_keywords = excluded_keywords or []
    best_address = None
    best_score = -1
    for address in _iter_arena_addresses(maze):
        normalized_address = _normalize_text(address)
        if any(keyword in normalized_address for keyword in excluded_keywords):
            continue
        score = sum(1 for keyword in preferred_keywords if keyword in normalized_address)
        if score > best_score and score > 0:
            best_address = address
            best_score = score
    return best_address


def resolve_known_object_address(persona, target=None, detail=None):
    combined_text = _combined_text(target, detail)
    for canonical_name, hints in KNOWN_OBJECT_HINTS.items():
        if any(hint in combined_text for hint in hints):
            for candidate_name in [canonical_name] + hints:
                address = persona.s_mem.find_nearest_object(candidate_name)
                if address:
                    return address, candidate_name, "known_object"
    return None, None, None


def resolve_known_arena_address(maze, target=None, detail=None):
    combined_text = _combined_text(target, detail)
    for rule in KNOWN_ARENA_RULES:
        if any(trigger in combined_text for trigger in rule["triggers"]):
            arena_address = _find_matching_arena_address(
                maze,
                rule["preferred_keywords"],
                rule.get("excluded_keywords", []),
            )
            if arena_address:
                return arena_address, arena_address.split(":")[-1], "known_arena"
    return None, None, None
